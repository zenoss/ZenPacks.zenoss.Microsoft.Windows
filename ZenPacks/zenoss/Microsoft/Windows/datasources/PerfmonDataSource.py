##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
DataSource that collects Perfmon counters from Windows.

Collection is performed by executing the Get-Counter PowerShell Cmdlet
via WinRS.
'''

import re
import logging
import collections
import time

from twisted.internet import defer, reactor
from twisted.internet.error import ConnectError, TimeoutError
from twisted.web.error import Error
from twisted.python.failure import Failure

from twisted.internet.task import LoopingCall

from zope.component import adapts, queryUtility
from zope.interface import implements

from Products.ZenCollector.interfaces import ICollectorPreferences
from Products.ZenEvents import ZenEventClasses
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.infos.template import RRDDataSourceInfo
from Products.Zuul.interfaces import IRRDDataSourceInfo
from Products.Zuul.utils import ZuulMessageFactory as _t

from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource import (
    PythonDataSource,
    PythonDataSourcePlugin,
)

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
from ..utils import append_event_datasource_plugin, errorMsgCheck, generateClearAuthEvents

from ..txcoroutine import coroutine

# Requires that txwinrm_utils is already imported.
from txwinrm.WinRMClient import SingleCommandClient, LongCommandClient
from txwinrm.util import UnauthorizedError, RequestError
from txwinrm.twisted_utils import add_timeout
import codecs
from . import send_to_debug

LOG = logging.getLogger('zen.MicrosoftWindows')

ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
SOURCETYPE = 'Windows Perfmon'

# This should match OperationTimeout in txwinrm's receive.xml.
OPERATION_TIMEOUT = 60
# Store corrupt counters for each device in module scope, not to doublecheck
# them when configuration for the device changes.
CORRUPT_COUNTERS = collections.defaultdict(list)
MAX_NETWORK_FAILURES = 3


class PowerShellError(Error):
    pass


class PerfmonDataSource(PythonDataSource):
    ZENPACKID = ZENPACKID

    sourcetype = SOURCETYPE
    sourcetypes = (SOURCETYPE,)

    plugin_classname = (
        ZENPACKID + '.datasources.PerfmonDataSource.PerfmonDataSourcePlugin')

    # Defaults for PythonDataSource user-facing properties.
    cycletime = '${here/zWinPerfmonInterval}'

    # Defaults for local user-facing properties.
    counter = ''

    _properties = PythonDataSource._properties + (
        {'id': 'counter', 'type': 'string'},
    )


class IPerfmonDataSourceInfo(IRRDDataSourceInfo):
    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    counter = schema.TextLine(
        group=_t(SOURCETYPE),
        title=_t('Counter'))


class PerfmonDataSourceInfo(RRDDataSourceInfo):
    implements(IPerfmonDataSourceInfo)
    adapts(PerfmonDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    counter = ProxyProperty('counter')


class PluginStates(object):
    STARTING = 'STARTING'
    STARTED = 'STARTED'
    STOPPING = 'STOPPING'
    STOPPED = 'STOPPED'


class DataPersister(object):

    """Cache of data collected from devices.

    Designed to be used in module scope to preserve data that comes in
    between the return of a plugin's collect and cleanup calls.

    """

    # Dictionary containing data for all monitored devices.
    devices = None

    # For performing periodic cleanup of stale data.
    maintenance_interval = 300

    # Data older than this (in seconds) will be dropped on maintenance.
    max_data_age = 3600

    def __init__(self):
        self.looping_call = LoopingCall(self.maintenance)
        self.devices = {}

    def start(self, result=None):
        if result:
            LOG.debug("Windows Perfmon data maintenance failed: {}".format(result))

        if not self.looping_call.running:
            LOG.debug("Windows Perfmon starting data maintenance")
            d = self.looping_call.start(self.maintenance_interval)
            d.addBoth(self.start)

    def maintenance(self):
        LOG.debug("Windows Perfmon performing periodic data maintenance")
        for device, data in self.devices.items():
            data_age = time.time() - data['last']
            if data_age > self.max_data_age:
                LOG.debug(
                    "dropping data for %s (%d seconds old)",
                    device, data_age)

                self.remove(device)

    def touch(self, device):
        if device not in self.devices:
            self.devices[device] = {
                'last': time.time(),
                'values': collections.defaultdict(dict),
                'events': [],
                'maps': [],
            }

    def get(self, device):
        return self.devices[device].copy()

    def get_events(self, device):
        self.touch(device)
        return self.devices[device]['events']

    def remove(self, device):
        if device in self.devices:
            del(self.devices[device])

    def add_event(self, device, datasources, event):
        self.touch(device)
        append_event_datasource_plugin(datasources, self.devices[device]['events'], event)

    def add_value(self, device, component, datasource, value, collect_time):
        self.touch(device)
        self.devices[device]['values'][component][datasource] = (
            value, collect_time)

    def pop(self, device):
        if device in self.devices:
            data = self.get(device)
            self.remove(device)
            return data


# Module-scoped to allow persistence of data across recreation of
# collector tasks.
PERSISTER = DataPersister()


class ComplexLongRunningCommand(object):
    """A complex command containing one or more long running commands,
    according to the number of commands supplied.
    """

    def __init__(self, dsconf, num_commands, unique_id):
        self.dsconf = dsconf
        self.unique_id = unique_id
        self.num_commands = num_commands
        self.commands = self._create_commands(num_commands)
        self.ps_command = 'powershell -NoLogo -NonInteractive -NoProfile -Command '
        self._shells = {}

    def get_id(self, cmd):
        try:
            return self._shells[cmd]
        except Exception:
            return None

    def store_ids(self, shells):
        """Store ids for each command.

        each command will have unique shell_cmd so this will shake out
        each command's shell and command ids.
        """
        for cmd in self.commands:
            try:
                shell_cmd = set(cmd._shells).intersection(shells).pop()
            except KeyError:
                # shouldn't happen, catch anyway
                continue
            self._shells[cmd] = shell_cmd

    def _create_commands(self, num_commands):
        """Create initial set of commands according to the number supplied."""
        self.num_commands = num_commands

        commands = []
        if num_commands == 0:
            return commands
        try:
            conn_info = createConnectionInfo(self.dsconf)
        except UnauthorizedError as e:
            error = "{0}: Windows Perfmon connection info is not available"\
                    " for {0}. Error: {1}".format(self.dsconf.device, e)
            LOG.error(error)
            PERSISTER.add_event(self.unique_id, [self.dsconf], {
                'device': self.dsconf.device,
                'eventClass': '/Status/Winrm',
                'eventKey': 'WindowsPerfmonCollection',
                'severity': ZenEventClasses.Warning,
                'summary': 'Windows Perfmon connection info is not available',
                'message': error})
        else:
            # allow for collection from sql clusters where active sql instance
            # could be running on different node from current host server
            # ex. sol-win03.solutions-wincluster.loc//SQL1 for MSSQLSERVER
            # sol-win03.solutions-wincluster.loc//SQL3\TESTINSTANCE1
            #       for TESTINSTANCE1
            # standalone ex.
            #       //SQLHOSTNAME for MSSQLSERVER
            #       //SQLTEST\TESTINSTANCE1 for TESTINSTANCE1
            if getattr(self.dsconf, 'cluster_node_server', None) and\
                    self.dsconf.params['owner_node_ip']:
                owner_node, server =\
                    self.dsconf.cluster_node_server.split('//')
                if owner_node:
                    conn_info = conn_info._replace(hostname=owner_node)
                    conn_info = conn_info._replace(
                        ipaddress=self.dsconf.params['owner_node_ip'])
            for _ in xrange(num_commands):
                try:
                    commands.append(LongCommandClient(conn_info))
                except Exception as e:
                    LOG.error("{}: Windows Perfmon error: {}".format(
                        self.dsconf.device, e))

        return commands

    def start(self, command_lines):
        """Start a separate command for each command line.

        If the number of commands has changed since the last start,
        create an appropriate set of commands.
        """
        deferreds = []
        if self.num_commands != len(command_lines):
            self.commands = self._create_commands(len(command_lines))

        for command, command_line in zip(self.commands, command_lines):
            LOG.debug('{}: Starting Perfmon collection script: {}'.format(
                self.dsconf.device, command_line))
            if command is not None:
                deferreds.append(add_timeout(command.start(self.ps_command,
                                                           ps_script=command_line),
                                             self.dsconf.zWinRMConnectTimeout))

        return defer.DeferredList(deferreds, consumeErrors=True)

    @coroutine
    def stop(self):
        """Stop all started commands."""
        for command in self.commands:
            shell_cmd = self.get_id(command)
            yield command.stop(shell_cmd)
            if shell_cmd:
                self._shells.pop(command)


class PerfmonDataSourcePlugin(PythonDataSourcePlugin):
    proxy_attributes = ConnectionInfoProperties + (
        'cluster_node_server',
    )

    config = None
    cycling = None
    state = None
    receive_deferreds = None
    data_deferred = None
    command = None
    sample_interval = None
    sample_buffer = collections.deque([])
    max_samples = None
    collected_samples = None
    counter_map = None

    ps_mod_path_msg = "Received \"The term 'New-Object' is not recognized as the name of a cmdlet,"\
                      " function, script file, or operable program.\"  Validate the default"\
                      " system PSModulePath environment variable."

    command_line = (
        '"& {{'
        '[System.Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($False); '
        '$FormatEnumerationLimit = -1; '
        '$Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size (4096, 1024); '
        'get-counter -ea silentlycontinue '
        '-SampleInterval {SampleInterval} -MaxSamples {MaxSamples} '
        '-counter @({Counters}) '
        '| Format-List -Property Readings;'
        ' }}"'
    )

    def __init__(self, config):
        self.config = config
        self.cycletime = config.datasources[0].cycletime

        preferences = queryUtility(ICollectorPreferences, 'zenpython')
        self.cycling = preferences.options.cycle

        # Define SampleInterval and MaxSamples arguments for ps commands.
        if self.cycling:
            self.sample_interval = self.cycletime
            self.max_samples = max(600 / self.sample_interval, 1)
        else:
            self.sample_interval = 1
            self.max_samples = 1

        self._start_counter = 0
        # Get counters from all components in the device.
        self.counter_map = {}
        self.ps_counter_map = {}
        for dsconf in self.config.datasources:
            counter = dsconf.params['counter'].decode('utf-8').lower()
            if counter not in self.counter_map:
                self.counter_map[counter] = []
                self.ps_counter_map[counter] = []
            self.counter_map[counter].append((dsconf.component, dsconf.datasource, dsconf.eventClass))
            self.ps_counter_map[counter].append((dsconf.component, dsconf.datasource))

        self._build_commandlines()

        self.unique_id = '_'.join((self.config.id, str(self.cycletime)))
        self._shells = []
        self.reset()

    def reset(self):
        self.state = PluginStates.STOPPED
        self.network_failures = 0

        self.complex_command = ComplexLongRunningCommand(
            self.config.datasources[0],
            self.num_commands,
            self.unique_id)

    def _build_commandlines(self):
        """Return a list of command lines needed to get data for all counters."""
        # The max length of the cmd.exe command is 8192.
        # The length of the powershell command line is ~ 420 chars.
        # Thus the line containing counters should not go beyond 7700 limit.
        counters_limit = 7700

        counters = sorted(self.ps_counter_map.keys())
        if not counters:
            self.num_commands = 0
            return

        # The number of long running commands needed to get data for all
        # counters of the device equals to floor division of the current
        # counters_line length by the calculated limit, incremented by 1.
        self.num_commands = len(format_counters(counters)) // counters_limit + 1
        LOG.debug('{}: Windows Perfmon Creating {} long running command(s)'.format(
            self.config.id,
            self.num_commands))

        # Chunk a counter list into num_commands equal parts.
        counters = chunkify(counters, self.num_commands)

        self.commandlines = [self.command_line.format(
            SampleInterval=self.sample_interval,
            MaxSamples=self.max_samples,
            Counters=format_counters(counter_group)
        ) for counter_group in counters]

    @classmethod
    def config_key(cls, datasource, context):
        return (
            context.device().id,
            datasource.getCycleTime(context),
            getattr(context, 'cluster_node_server', ''),
            SOURCETYPE,
        )

    @classmethod
    def params(cls, datasource, context):
        counter = datasource.talesEval(datasource.counter, context)
        if getattr(context, 'perfmonInstance', None):
            if not re.match("\\\\.*\\\\.*", counter):
                counter = ''.join((context.perfmonInstance, counter))

        owner_node_ip = None
        if hasattr(context, 'cluster_node_server'):
            owner_node, _ = context.cluster_node_server.split('//')
            owner_node_ip = getattr(context, 'owner_node_ip', None)
            if not owner_node_ip:
                try:
                    owner_node_ip = context.device().clusterhostdevicesdict.get(owner_node, None)
                except Exception:
                    pass

        return {
            'counter': counter,
            'owner_node_ip': owner_node_ip
        }

    @coroutine
    def collect(self, config):
        """Collect for config.

        Called each collection interval.
        """
        self._start_counter += 1
        if self.num_commands == 0:
            # nothing to do, return
            data = self.new_data()
            msg = '{} has no Get-Counter commands to start due to corrupt '\
                  'or missing counters.'.format(config.id)
            data['events'].append({
                'device': self.config.id,
                'eventClass': '/Status/Winrm',
                'eventKey': 'WindowsPerfmonCollection',
                'severity': ZenEventClasses.Warning,
                'summary': msg,
                'ipAddress': self.config.manageIp})
            self.state = PluginStates.STOPPED
            defer.returnValue(data)

        # double check to make sure we aren't continuing to try
        # and receive from a finished collection
        if self._start_counter > self.max_samples:
            yield self.stop()
        yield self.start()

        data = yield self.get_data()
        try:
            evt_summaries = [x.get('summary', '') for x in data['events']]
        except Exception:
            evt_summaries = []
        if self.ps_mod_path_msg in evt_summaries:
            # don't clear powershell event
            # remove clear event
            for evt in data['events']:
                if evt.get('eventKey', '') == 'WindowsPerfmonCollection'\
                        and evt.get('severity', -1) == 0:
                    data['events'].remove(evt)
        defer.returnValue(data)

    @coroutine
    def start(self):
        """Start the continuous command."""
        if self.state != PluginStates.STOPPED:
            defer.returnValue(None)

        self._start_counter = 0
        shells = []

        LOG.debug("Windows Perfmon starting Get-Counter on %s", self.config.id)
        self.state = PluginStates.STARTING

        try:
            # complex_command.start returns a DeferredList with baked-in timeouts
            results = yield self.complex_command.start(self.commandlines)
        except Exception as e:
            errorMessage = "Windows Perfmon Error on {}: {}".format(
                self.config.id,
                e.message or "timeout")
            LOG.warn("{}: {}".format(self.config.id, errorMessage))

            # prevent duplicate of auth failure messages
            if not errorMsgCheck(self.config, PERSISTER.get_events(self.unique_id), e.message):
                PERSISTER.add_event(self.unique_id, self.config.datasources, {
                    'device': self.config.id,
                    'eventClass': '/Status/Winrm',
                    'eventKey': 'WindowsPerfmonCollection',
                    'severity': ZenEventClasses.Warning,
                    'summary': errorMessage,
                    'ipAddress': self.config.manageIp})

            self.state = PluginStates.STOPPED
            defer.returnValue(None)

        # check to see if commands started
        for success, data in results:
            if success:
                self.state = PluginStates.STARTED
                shells.append(data)
            else:
                errorMessage = 'Perfmon command(s) did not start'
                reason = str(data.value)
                LOG.warn("%s: %s: %s", self.config.id, errorMessage, reason)
                if not errorMsgCheck(self.config, PERSISTER.get_events(self.unique_id), reason):
                    PERSISTER.add_event(self.unique_id, self.config.datasources, {
                        'device': self.config.id,
                        'eventClass': '/Status/Winrm',
                        'eventKey': 'WindowsPerfmonCollection',
                        'severity': ZenEventClasses.Warning,
                        'summary': errorMessage + ': ' + reason,
                        'ipAddress': self.config.manageIp})

        if self.state != PluginStates.STARTED:
            self.state = PluginStates.STOPPED
        else:
            PERSISTER.add_event(self.unique_id, self.config.datasources, {
                'device': self.config.id,
                'eventClass': '/Status/Winrm',
                'eventKey': 'WindowsPerfmonCollection',
                'severity': ZenEventClasses.Clear,
                'summary': 'successfully started Get-Counter command(s)',
                'ipAddress': self.config.manageIp})
        self.collected_samples = 0
        self.collected_counters = set()
        self.complex_command.store_ids(shells)

        self.receive()

        # When running in the foreground without the --cycle option we
        # must wait for the receive deferred to fire to have any chance
        # at collecting data.
        if not self.cycling and self.receive_deferreds:
            yield self.receive_deferreds

        PERSISTER.start()
        defer.returnValue(None)

    @coroutine
    def get_data(self):
        """Wait for data to arrive if necessary, then return it."""
        data = PERSISTER.pop(self.unique_id)
        if self.state == PluginStates.STOPPED:
            defer.returnValue(data)
        if data and data['values']:
            defer.returnValue(data)
        if data and data['events']:
            for evt in data['events']:
                PERSISTER.add_event(self.unique_id, self.config.datasources, evt)

        if hasattr(self, '_wait_for_data'):
            LOG.debug("Windows Perfmon waiting for %s Get-Counter data", self.config.id)
            self.data_deferred = defer.Deferred()
            try:
                yield add_timeout(
                    self.data_deferred,
                    self.config.datasources[0].zWinRMConnectTimeout)
            except Exception:
                pass
        else:
            self._wait_for_data = True

        defer.returnValue(PERSISTER.pop(self.unique_id))

    @coroutine
    def stop(self):
        """Stop the continuous command."""
        if self.state != PluginStates.STARTED:
            LOG.debug(
                "Windows Perfmon skipping Get-Counter stop on %s while it's %s",
                self.config.id,
                self.state)

            defer.returnValue(None)

        LOG.debug("stopping Get-Counter on %s", self.config.id)

        self.state = PluginStates.STOPPING

        if self.receive_deferreds:
            try:
                self.receive_deferreds.cancel()
            except Exception:
                pass

        if self.complex_command:
            try:
                yield self.complex_command.stop()
            except (RequestError, Exception) as ex:
                if 'the request contained invalid selectors for the resource' in ex.message:
                    # shell was lost due to reboot, service restart, or other circumstance
                    LOG.debug('Perfmon shell on {} was destroyed.  Get-Counter'
                              ' will attempt to restart on the next cycle.')
                else:
                    if 'canceled by the user' in ex.message or\
                            'OperationTimeout' in ex.message:
                        # This means the command finished naturally before
                        # we got a chance to stop it. Totally normal.
                        # Or there was an OperationTimeout, also not
                        # Warning worthy
                        log_level = logging.DEBUG
                    else:
                        # Otherwise this could result in leaking active
                        # operations on the Windows server and should be
                        # logged as a warning.
                        log_level = logging.WARN

                    LOG.log(
                        log_level,
                        "Windows Perfmon failed to stop Get-Counter on %s: %s",
                        self.config.id, ex)

        self.state = PluginStates.STOPPED

        defer.returnValue(None)

    @coroutine
    def restart(self):
        """Stop then start the long-running command."""
        yield self.stop()
        yield self.start()
        defer.returnValue(None)

    def receive(self):
        """Receive results from continuous command."""
        deferreds = []
        for cmd in self.complex_command.commands:
            if cmd is not None:
                try:
                    shell_cmd = self.complex_command.get_id(cmd)
                    if shell_cmd:
                        deferreds.append(cmd.receive(shell_cmd))
                except Exception as err:
                    LOG.error('{}: Windows Perfmon receive error {}'.format(
                        self.config.id, err))

        if deferreds:
            self.receive_deferreds = defer.DeferredList(deferreds,
                                                        consumeErrors=True)

            self.receive_deferreds.addCallbacks(
                self.onReceive, self.onReceiveFail)

    def _parse_deferred_result(self, result):
        """Parse out results from deferred response.

        Group all stdout data and failures from each command result
        and return them as a tuple of two lists: (filures, results)
        """
        failures, results = [], []

        for index, command_result in enumerate(result):
            # The DeferredList result is of type:
            # [(True/False, [stdout, stderr]/failure), ]
            success, data = command_result
            if success:
                stdout, stderr = data.stdout, data.stderr
                # Log error message if present.
                if stderr:
                    ps_error = ' '.join(stderr)
                    LOG.debug('stderr: {}'.format(ps_error))
                    if "Attempting to perform the InitializeDefaultDrives operation on the 'FileSystem' provider failed." in ps_error:
                        failures.append(Failure(PowerShellError(500, message=ps_error)))
                    if 'not recognized as the name of a cmdlet' in ps_error:
                        failures.append(Failure(PowerShellError(500, message=ps_error)))
                        # could be ZPS-3517 and 'double-hop issue'
                        PERSISTER.add_event(self.unique_id, self.config.datasources, {
                            'device': self.config.id,
                            'eventClass': '/Status/Winrm',
                            'eventKey': 'WindowsPerfmonCollection',
                            'severity': ZenEventClasses.Warning,
                            'summary': self.ps_mod_path_msg,
                            'ipAddress': self.config.manageIp})

                # Leave sample start marker in first command result
                # to properly report missing counters.
                if index == 0:
                    results.extend(stdout)
                else:
                    results.extend(format_stdout(stdout)[0])
            else:
                failures.append(data)

        return failures, results

    @coroutine
    def onReceive(self, result):
        """Group the result of all commands into a single result."""
        failures, results = self._parse_deferred_result(result)

        LOG.debug("Get-Counter results: {} {}".format(self.config.id, result))
        collect_time = int(time.time())

        # Initialize sample buffer. Start of a new sample.
        stdout_lines, sample_start = format_stdout(results)

        if stdout_lines:
            LOG.debug("Windows Perfmon received Get-Counter data for %s", self.config.id)
            # Data persister will take care of data order.
            self.sample_buffer = collections.deque(stdout_lines)

            if sample_start:
                self.collected_samples += 1

        # Continue while we have counter/value pairs.
        while len(self.sample_buffer) > 1:
            # Make sure no exceptions happen here. Otherwise all data
            # collection would go down.
            try:
                # Buffer to counter conversion:
                #   '\\\\amazona-q2r281f\\web service(another web site)\\move requests/sec :'
                #   '\\\\amazona-q2r281f\\web service(another web site)\\move requests/sec'
                #   '\\web service(another web site)\\move requests/sec'
                counter = '\\{}'.format(
                    self.sample_buffer.popleft().strip(' :').split('\\', 3)[3]).decode('utf-8')

                value = self.sample_buffer.popleft()

                # ZEN-12024: Some locales use ',' as the decimal point.
                if ',' in value:
                    value = value.replace(',', '.', 1)

                comp_ds_ec_l = self.counter_map.get(counter, [])
                for component, datasource, event_class in comp_ds_ec_l:
                    if datasource:
                        self.collected_counters.add(counter)

                        # We special-case the sysUpTime datapoint to convert
                        # from seconds to centi-seconds. Due to its origin in
                        # SNMP monitor Zenoss expects uptime in centi-seconds
                        # in many places.
                        if datasource == 'sysUpTime' and value is not None:
                            value = float(value) * 100

                        PERSISTER.add_value(
                            self.unique_id, component, datasource, value, collect_time)
            except Exception, err:
                LOG.debug('{}: Windows Perfmon could not process a sample. Error: {}'.format(self.config.id, err))

        if self.data_deferred and not self.data_deferred.called:
            self.data_deferred.callback(None)

        # Report missing counters every sample interval.
        if self.collected_counters and self.collected_samples >= 0:
            self.reportMissingCounters(
                self.counter_map, self.collected_counters)
            # Reinitialize collected counters for reporting.
            self.collected_counters = set()

        # Log error message and wait for the data.
        if failures and not results:
            # No need to call onReceiveFail for each command in DeferredList.
            yield self.onReceiveFail(failures[0])

        # Continue to receive if MaxSamples value has not been reached yet.
        elif self.collected_samples < self.max_samples and results:
            self.receive()

        # In case ZEN-12676/ZEN-11912 are valid issues.
        elif not results and not failures and self.cycling:
            try:
                yield add_timeout(
                    self.remove_corrupt_counters(),
                    self.config.datasources[0].zWinRMConnectTimeout)
            except Exception:
                pass
            if self.ps_counter_map.keys():
                yield self.restart()
            # Report corrupt counters
            dsconf0 = self.config.datasources[0]
            if CORRUPT_COUNTERS[dsconf0.device]:
                self.reportCorruptCounters(self.counter_map)
        else:
            if self.cycling:
                LOG.debug('{}: Windows Perfmon Result: {}'.format(self.config.id, result))
                yield self.restart()

        generateClearAuthEvents(self.config, PERSISTER.get_events(self.unique_id))

        PERSISTER.add_event(self.unique_id, self.config.datasources, {
            'device': self.config.id,
            'eventClass': '/Status/Winrm',
            'eventKey': 'WindowsPerfmonCollection',
            'severity': ZenEventClasses.Clear,
            'summary': 'Successful Perfmon Collection',
            'ipAddress': self.config.manageIp})
        defer.returnValue(None)

    @coroutine
    def onReceiveFail(self, failure):
        e = failure.value

        if isinstance(e, defer.CancelledError):
            return

        retry, level, msg = (False, None, None)  # NOT USED.

        if isinstance(e.message, list):
            errorMsg = ' '.join([str(i) for i in e.message])
        else:
            errorMsg = e.message
        if not errorMsgCheck(self.config, PERSISTER.get_events(self.unique_id), errorMsg):
            generateClearAuthEvents(self.config, PERSISTER.get_events(self.unique_id))
        # Handle errors on which we should retry the receive.
        if 'OperationTimeout' in e.message:
            # do not log operation timeout message.  it implies there's some sort of problem.
            # we expect to see this timeout during default zWinPerfmonInterval time (300)
            # it only adds confusion to troubleshooters.  we'll just retry and return
            self.receive()
            defer.returnValue(None)

        elif "Attempting to perform the InitializeDefaultDrives operation on the 'FileSystem' provider failed." in e.message:
            retry, level, msg = (
                True,
                logging.DEBUG,
                "Ignoring powershell error on {} as it does not affect collection: {}"
                .format(self.config.id, e))
        elif '500' in e.message:
            if 'decrypt' in e.message:
                retry, level, msg = (
                    True,
                    logging.DEBUG,
                    'got debug integrity check during receive.  '
                    'attempting to receive again'
                )
            elif 'internal error' in e.message:
                retry, level, msg = (
                    True,
                    logging.DEBUG,
                    'got internal error during receive.  '
                    'attempting to receive again'
                )
            elif 'unexpected response' in e.message.lower():
                retry, level, msg = (
                    True,
                    logging.DEBUG,
                    'got "Unexpected Response" during receive, '
                    'attempting to receive again'
                )
            else:
                retry, level, msg = (
                    True,
                    logging.DEBUG,
                    errorMsg
                )
        elif isinstance(e, ConnectError):
            retry, level, msg = (
                isinstance(e, TimeoutError),
                logging.WARN,
                "network error on {}: {}"
                .format(self.config.id, e.message or 'timeout'))
            if isinstance(e, TimeoutError):
                self.network_failures += 1
        elif isinstance(e, PowerShellError):
            level, msg = (logging.WARN, self.ps_mod_path_msg)
        # Handle errors on which we should start over.
        else:
            level = logging.WARN
            if send_to_debug(failure):
                level = logging.DEBUG
            elif isinstance(e, AttributeError) and \
                    "'NoneType' object has no attribute 'persistent'" in e.message:
                level = logging.DEBUG
                e = 'Attempted to receive from closed connection.  Possibly '\
                    'due to device reboot.'
            elif 'invalid selectors for the resource' in e.message:
                level = logging.DEBUG
                e = 'Attempted to use a non-existent remote shell.  Possibly '\
                    'due to device reboot.'
            retry, msg = (
                False,
                "receive failure on {}: {}"
                .format(self.config.id, e))

        if self.data_deferred and not self.data_deferred.called:
            self.data_deferred.errback(failure)

        LOG.log(level, msg)
        if self.network_failures >= MAX_NETWORK_FAILURES:
            yield self.stop()
            self.reset()
            retry = False
        if retry:
            self.receive()
        else:
            yield self.stop()
            self.reset()

        defer.returnValue(None)

    @coroutine
    def search_corrupt_counters(self, winrs, counter_list, corrupt_list):
        """Bisect the counters to determine which of them are corrupt."""
        ps_command = "powershell -NoLogo -NonInteractive -NoProfile -Command"
        ps_script = lambda counters: (
            "\"get-counter -counter @({})\"".format(format_counters(counters)))

        num_counters = len(counter_list)

        if num_counters == 0:
            pass
        elif num_counters == 1:
            result = yield add_timeout(winrs.run_command(ps_command, ps_script(counter_list)),
                                       OPERATION_TIMEOUT + 5)
            if result.stderr:
                if 'not recognized as the name of a cmdlet' in result.stderr:
                    PERSISTER.add_event(self.unique_id, self.config.datasources, {
                        'device': self.config.id,
                        'severity': ZenEventClasses.Error,
                        'eventClass': '/Status/Winrm',
                        'eventKey': 'WindowsPerfmonCollection',
                        'summary': self.ps_mod_path_msg,
                    })
                    defer.returnValue(corrupt_list)

                LOG.debug('Received error checking for corrupt counter: %s', result.stderr)
                # double check that no counter sample was returned
                if not counter_returned(result):
                    corrupt_list.extend(counter_list)
        else:
            mid_index = num_counters / 2
            slices = (counter_list[:mid_index], counter_list[mid_index:])
            for counter_slice in slices:
                result = yield add_timeout(winrs.run_command(ps_command, ps_script(counter_slice)),
                                           OPERATION_TIMEOUT + 5)
                if result.stderr:
                    yield self.search_corrupt_counters(
                        winrs, counter_slice, corrupt_list)

        defer.returnValue(corrupt_list)

    @coroutine
    def remove_corrupt_counters(self):
        """Remove counters which return an error."""
        LOG.debug('{}: Performing check for corrupt counters'.format(self.config.id))
        dsconf0 = self.config.datasources[0]
        winrs = SingleCommandClient(createConnectionInfo(dsconf0))

        counter_list = sorted(
            set(self.ps_counter_map.keys()) - set(CORRUPT_COUNTERS[dsconf0.device]))
        corrupt_counters = yield self.search_corrupt_counters(winrs, counter_list, [])

        # Add newly found corrupt counters to the previously checked ones.
        if corrupt_counters:
            CORRUPT_COUNTERS[dsconf0.device].extend(corrupt_counters)

        # Remove the error counters from the counter map.
        for counter in CORRUPT_COUNTERS[dsconf0.device]:
            if self.ps_counter_map.get(counter):
                LOG.debug("Counter '{0}' not found. Removing".format(counter))
                del self.ps_counter_map[counter]

        # Rebuild the command.
        self._build_commandlines()

        defer.returnValue(None)

    def reportCorruptCounters(self, requested):
        """Emit event for corrupt counters"""
        default_eventClass = '/Status/Winrm'
        dsconf0 = self.config.datasources[0]

        events = {}
        for req_counter in requested:
            if req_counter in CORRUPT_COUNTERS[dsconf0.device]:
                comp_ds_ec_l = requested.get(req_counter, [])
                for component, datasource, event_class in comp_ds_ec_l:
                    if event_class and event_class != default_eventClass:
                        if event_class not in events:
                            events[event_class] = []
                        events[event_class].append(req_counter)
                    else:
                        if default_eventClass not in events:
                            events[default_eventClass] = []
                        events[default_eventClass].append(req_counter)

        if events:
            for event in events:
                PERSISTER.add_event(self.unique_id, self.config.datasources, {
                    'device': self.config.id,
                    'severity': ZenEventClasses.Error,
                    'eventClass': event,
                    'eventKey': 'Windows Perfmon Corrupt Counters',
                    'summary': self.corrupt_counters_summary(len(events[event])),
                    'corrupt_counters': self.missing_counters_str(events[event]).decode('UTF-8'),
                })

        for req_counter in requested:
            comp_ds_ec_l = requested.get(req_counter, [])
            for component, datasource, event_class in comp_ds_ec_l:
                event_class = event_class or default_eventClass
                if event_class not in events:
                    PERSISTER.add_event(self.unique_id, self.config.datasources, {
                        'device': self.config.id,
                        'severity': ZenEventClasses.Clear,
                        'eventClass': event_class or default_eventClass,
                        'eventKey': 'Windows Perfmon Corrupt Counters',
                        'summary': '0 counters corrupt in collection',
                    })

    def reportMissingCounters(self, requested, returned):
        """Emit logs and events for counters requested but not returned."""
        missing_counters = set(requested).difference(returned)
        default_eventClass = '/Status/Winrm'

        events = {}
        for req_counter in requested:
            if req_counter in missing_counters:
                comp_ds_ec_l = requested.get(req_counter, [])
                for component, datasource, event_class in comp_ds_ec_l:
                    if event_class and event_class != default_eventClass:
                        if event_class not in events:
                            events[event_class] = []
                        events[event_class].append(req_counter)
                    else:
                        if default_eventClass not in events:
                            events[default_eventClass] = []
                        events[default_eventClass].append(req_counter)

        if events:
            for event in events:
                PERSISTER.add_event(self.unique_id, self.config.datasources, {
                    'device': self.config.id,
                    'severity': ZenEventClasses.Info,
                    'eventClass': event,
                    'eventKey': 'Windows Perfmon Missing Counters',
                    'summary': self.missing_counters_summary(len(events[event])),
                    'missing_counters': self.missing_counters_str(events[event]).decode('UTF-8'),
                })

        for req_counter in requested:
            comp_ds_ec_l = requested.get(req_counter, [])
            for component, datasource, event_class in comp_ds_ec_l:
                event_class = event_class or default_eventClass
                if event_class not in events:
                    PERSISTER.add_event(self.unique_id, self.config.datasources, {
                        'device': self.config.id,
                        'severity': ZenEventClasses.Clear,
                        'eventClass': event_class or default_eventClass,
                        'eventKey': 'Windows Perfmon Missing Counters',
                        'summary': '0 counters missing in collection',
                    })

    def missing_counters_summary(self, count):
        return (
            '{} counters missing in collection - see details'.format(count))

    def corrupt_counters_summary(self, count):
        return (
            '{} counters found corrupted in collection - see details'.format(count))

    def missing_counters_str(self, counters):
        return ', '.join(counters)

    def cleanup(self, config):
        """Cleanup any resources associated with this task.

        This can happen when zenpython terminates, or anytime config is
        deleted or modified.
        """
        return reactor.callLater(self.sample_interval, self.stop)

    def _errorMsgCheck(self, errorMessage):
        """Check error message and generate appropriate event."""
        wrongCredsMessages = ('Check username and password', 'Username invalid', 'Password expired')
        if any(x in errorMessage for x in wrongCredsMessages):
            PERSISTER.add_event(self.unique_id, self.config.datasources, {
                'device': self.config.id,
                'eventClassKey': 'AuthenticationFailure',
                'summary': errorMessage,
                'ipAddress': self.config.manageIp})
            return True
        return False

    def _generateClearAuthEvents(self):
        """Add clear authentication events to PERSISTER singleton."""
        PERSISTER.add_event(self.unique_id, self.config.datasources, {
            'device': self.config.id,
            'eventClassKey': 'AuthenticationSuccess',
            'summary': 'Authentication Successful',
            'severity': ZenEventClasses.Clear,
            'ipAddress': self.config.manageIp})


def counter_returned(result):
    if 'CounterSamples' in ''.join(result.stdout):
        return True
    return False


def format_counters(ps_counters):
    """Convert a list of supplied counters into a string, which will
    be further used to cteate ps command line.
    """
    counters = []
    for counter in ps_counters:
        # check for unicode apostrophe present in foreign langs
        counter = counter.replace(u'\u2019', "'+[char]8217+'")
        counters.append("('{0}')".format(counter))
    return ','.join(counters)


def chunkify(lst, n):
    """Yield successive n-sized chunks from the list."""
    return [lst[i::n] for i in xrange(n)]


def format_stdout(stdout_lines):
    """Return a tuple containing a list of stdout lines without the
    BOM marker and property name, and a bool value specifying if it
    is a start of a sample.
    """
    sample_start = False
    # Remove BOM marker(if present).
    if stdout_lines and stdout_lines[0] == unicode(codecs.BOM_UTF8, "utf8"):
        stdout_lines = stdout_lines[1:]

    # Remove property name from the first stdout line.
    if stdout_lines and stdout_lines[0].startswith('Readings : '):
        stdout_lines[0] = stdout_lines[0].replace('Readings : ', '', 1)
        sample_start = True

    return stdout_lines, sample_start
