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

from ..twisted_utils import add_timeout
from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
from ..utils import append_event_datasource_plugin, errorMsgCheck, generateClearAuthEvents

from ..txcoroutine import coroutine

# Requires that txwinrm_utils is already imported.
from txwinrm.shell import create_long_running_command
from txwinrm.WinRMClient import SingleCommandClient
from txwinrm.util import UnauthorizedError, RequestError
import codecs
from . import send_to_debug

LOG = logging.getLogger('zen.MicrosoftWindows')

ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
SOURCETYPE = 'Windows Counter'

# This should match OperationTimeout in txwinrm's receive.xml.
OPERATION_TIMEOUT = 60
# Store corrupt counters for each device in module scope, not to doublecheck
# them when configuration for the device changes.
CORRUPT_COUNTERS = collections.defaultdict(list)
MAX_NETWORK_FAILURES = 3


class CounterDataSource(PythonDataSource):
    ZENPACKID = ZENPACKID

    sourcetype = SOURCETYPE
    sourcetypes = (SOURCETYPE,)

    plugin_classname = (
        ZENPACKID + '.datasources.CounterDataSource.CounterDataSourcePlugin')

    # Defaults for PythonDataSource user-facing properties.
    cycletime = '${here/zWinPerfmonInterval}'

    # Defaults for local user-facing properties.
    object_instance = ''

    _properties = PythonDataSource._properties + (
        {'id': 'object_instance', 'type': 'string'},
    )


class ICounterDataSourceInfo(IRRDDataSourceInfo):
    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    object_instance = schema.TextLine(
        group=_t(SOURCETYPE),
        title=_t('Performance Object'))


class CounterDataSourceInfo(RRDDataSourceInfo):
    implements(ICounterDataSourceInfo)
    adapts(CounterDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    object_instance = ProxyProperty('object_instance')


class CounterDataSourcePlugin(PythonDataSourcePlugin):
    proxy_attributes = ConnectionInfoProperties

    config = None
    cycling = None
    state = None
    receive_deferreds = None
    data_deferred = None
    command = None
    sample_interval = None
    sample_buffer = collections.deque([])
    max_samples = None
    collected_samples = 0
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
        '-SampleInterval {SampleInterval} -MaxSamples 1 '
        '-counter @({Counters}) '
        '| Format-List -Property Readings;'
        ' }}"'
    )

    def __init__(self, config):
        self.config = config
        self.ds0 = config.datasources[0]
        self.cycletime = config.datasources[0].cycletime

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
        self.collected_samples = 0
        self.collected_counters = set()

        self._build_commandlines()

    def _build_commandlines(self):
        """Return a list of command lines needed to get data for all counters."""
        # The max length of the cmd.exe command is 8192.
        # The length of the powershell command line is ~ 420 chars.
        # Thus the line containing counters should not go beyond 7700 limit.
        counters_limit = 7700

        counters = sorted(self.ps_counter_map.keys())

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
            Counters=format_counters(counter_group),
            SampleInterval=self.sample_interval
        ) for counter_group in counters]

    @classmethod
    def config_key(cls, datasource, context):
        return (
            context.device().id,
            datasource.getCycleTime(context),
            SOURCETYPE,
        )

    @classmethod
    def params(cls, datasource, context):
        object_instance = datasource.talesEval(datasource.object_instance, context)
        return {'counter': object_instance}

    def _create_commands(self, num_commands):
        """Create initial set of commands according to the number supplied."""
        self.num_commands = num_commands

        commands = []
        try:
            conn_info = createConnectionInfo(self.ds0)
        except UnauthorizedError as e:
            LOG.error(
                "{0}: Windows Perfmon connection info is not available for {0}."
                " Error: {1}".format(self.ds0.device, e))
        else:
            for _ in xrange(num_commands):
                try:
                    commands.append(SingleCommandClient(conn_info))
                except Exception as e:
                    LOG.error("{}: Windows Perfmon error: {}".format(
                        self.ds0.device, e))

        return commands

    @coroutine
    def collect(self, config):
        """Collect for config.

        Called each collection interval.
        """
        self.ps_command = 'powershell -NoLogo -NonInteractive -NoProfile -Command '
        deferreds = []
        commands = self._create_commands(self.num_commands)
        for command, command_line in zip(commands, self.commandlines):
            LOG.debug('{}: Running Get-Counter collection script: {}'.format(self.ds0.device, command_line))
            if command is not None:
                deferreds.append(
                    add_timeout(
                        command.run_command(
                            self.ps_command,
                            ps_script=command_line),
                        self.ds0.zWinRMConnectTimeout))

        data = yield defer.DeferredList(deferreds)
        defer.returnValue(data)

    def _parse_deferred_result(self, result):
        """Group all stdout data and failures from each command result
        and return them as a tuple of two lists: (filures, results)
        """
        failures, results = [], []

        for index, command_result in enumerate(result):
            # The DeferredList result is of type:
            # [(True/False, CommandResponse/failure), ]
            success, data = command_result
            if success:
                stdout = data.stdout
                stderr = data.stderr
                # Log error message if present.
                if stderr:
                    ps_error = ' '.join(stderr)
                    LOG.debug(ps_error)
                    if 'not recognized as the name of a cmdlet' in ps_error:
                        # could be ZPS-3517 and 'double-hop issue'
                        self.data['events'].append({
                            'device': self.config.id,
                            'eventClass': '/Status/Winrm',
                            'eventKey': 'WindowsPerfmonCollection',
                            'severity': ZenEventClasses.Error,
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

    def onSuccess(self, results, config):
        """Group the result of all commands into a single result."""
        LOG.debug("Get-Counter results: {}".format(results))
        self.data = self.new_data()
        failures, results = self._parse_deferred_result(results)

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

                        self.data['values'][component][datasource] = value, collect_time
            except Exception, err:
                LOG.debug('{}: Windows Perfmon could not process a sample. Error: {}'.format(self.config.id, err))

        # Report missing counters every sample interval.
        if self.collected_counters and self.collected_samples >= 0:
            self.reportMissingCounters(
                self.counter_map, self.collected_counters)
            # Reinitialize collected counters for reporting.
            self.collected_counters = set()

        """
        # Log error message and wait for the data.
        if failures and not results:
            # No need to call onReceiveFail for each command in DeferredList.
            self.onReceiveFail(failures[0])
        # In case ZEN-12676/ZEN-11912 are valid issues.

        elif not results and not failures:
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
        """

        generateClearAuthEvents(self.config, self.data['events'])

        self.data['events'].append({
            'device': self.config.id,
            'eventKey': 'WindowsCounterCollection',
            'severity': ZenEventClasses.Clear,
            'summary': 'Successful Perfmon Collection',
            'ipAddress': self.config.manageIp})
        return self.data

    def onError(self, result, config):
        prefix = 'failed collection - '
        msg = 'WindowsCounterLog: {0}{1} {2}'.format(prefix, result, config)
        logg = LOG.error
        if send_to_debug(result):
            logg = LOG.debug
        logg(msg)
        data = self.new_data()
        if not errorMsgCheck(config, data['events'], result.value.message):
            data['events'].append({
                'severity': ZenEventClasses.Error,
                'eventKey': 'WindowsCounterCollection',
                'summary': msg,
                'device': config.id})
        return data

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
                    self.data['events'].append({
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
                self.data['events'].append({
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
                    self.data['events'].append({
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
                self.data['events'].append({
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
                    self.data['events'].append({
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
        # return reactor.callLater(self.sample_interval, self.stop)
        pass


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
