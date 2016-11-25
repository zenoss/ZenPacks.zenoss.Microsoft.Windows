##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2016, all rights reserved.
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

# Requires that txwinrm_utils is already imported.
from txwinrm.shell import create_long_running_command, create_single_shot_command
import codecs

LOG = logging.getLogger('zen.MicrosoftWindows')

ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
SOURCETYPE = 'Windows Perfmon'

# This should match OperationTimeout in txwinrm's receive.xml.
OPERATION_TIMEOUT = 60
# Store corrupt counters for each device in module scope, not to doublecheck
# them when configuration for the device changes.
CORRUPT_COUNTERS = collections.defaultdict(list)
MAX_NETWORK_FAILURES = 3


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
        self.devices = {}
        self.start()

    def start(self, result=None):
        if result:
            LOG.debug("data maintenance failed: %s", result)

        LOG.debug("starting data maintenance")
        d = LoopingCall(self.maintenance).start(self.maintenance_interval)
        d.addBoth(self.start)

    def maintenance(self):
        LOG.debug("performing periodic data maintenance")
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

    def remove(self, device):
        if device in self.devices:
            del(self.devices[device])

    def add_event(self, device, event):
        self.touch(device)
        self.devices[device]['events'].append(event)

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
    '''
    A complex command containing one or more long running commands,
    according to the number of commands supplied.
    '''

    def __init__(self, dsconf, num_commands):
        self.dsconf = dsconf
        self.num_commands = num_commands
        self.commands = self._create_commands(num_commands)

    def _create_commands(self, num_commands):
        '''
        Create initial set of commands according to the number supplied.
        '''
        self.num_commands = num_commands
        return [create_long_running_command(createConnectionInfo(self.dsconf))
                for i in xrange(num_commands)]

    @defer.inlineCallbacks
    def start(self, command_lines):
        '''
        Start a separate command for each command line.
        If the number of commands has changed since the last start,
        create an appropriate set of commands.
        '''
        if self.num_commands != len(command_lines):
            self.commands = self._create_commands(len(command_lines))

        for command, command_line in zip(self.commands, command_lines):
            yield command.start(command_line)

    @defer.inlineCallbacks
    def stop(self):
        '''
        Stop all started commands.
        '''
        for command in self.commands:
            yield command.stop()


class PerfmonDataSourcePlugin(PythonDataSourcePlugin):
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
    collected_samples = None
    counter_map = None

    command_line = (
        'powershell -NoLogo -NonInteractive -NoProfile -Command "& {{'
        '$CurrentCulture = [System.Threading.Thread]::CurrentThread.CurrentCulture;'
        '[System.Threading.Thread]::CurrentThread.CurrentCulture = New-Object \"System.Globalization.CultureInfo\" \"en-Us\";'
        'Invoke-Command {{ '
        '[System.Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($False); '
        '$FormatEnumerationLimit = -1; '
        '$Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size (4096, 25); '
        'get-counter -ea silentlycontinue '
        '-SampleInterval {SampleInterval} -MaxSamples {MaxSamples} '
        '-counter @({Counters}) '
        '| Format-List -Property Readings; }};'
        '[System.Threading.Thread]::CurrentThread.CurrentCulture = $CurrentCulture; }}"'
    )

    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self):
        self.state = PluginStates.STOPPED

        dsconf0 = self.config.datasources[0]
        preferences = queryUtility(ICollectorPreferences, 'zenpython')
        self.cycling = preferences.options.cycle

        # Define SampleInterval and MaxSamples arguments for ps commands.
        if self.cycling:
            self.sample_interval = dsconf0.cycletime
            self.max_samples = max(600 / self.sample_interval, 1)
        else:
            self.sample_interval = 1
            self.max_samples = 1

        # Get counters from all components in the device.
        self.counter_map = {}
        self.ps_counter_map = {}
        for dsconf in self.config.datasources:
            counter = dsconf.params['counter'].lower()
            ps_counter = convert_to_ps_counter(counter)
            self.counter_map[counter] = (dsconf.component, dsconf.datasource, dsconf.eventClass)
            self.ps_counter_map[ps_counter] = (dsconf.component, dsconf.datasource)

        self._build_commandlines()

        self.complex_command = ComplexLongRunningCommand(
            dsconf0, self.num_commands)
        self.network_failures = 0

    def _build_commandlines(self):
        '''
        Return a list of command lines needed to get data for all counters.
        '''
        # The max length of the cmd.exe command is 8192.
        # The length of the powershell prefix is ~ 680 chars.
        # Thus the line containing counters should not go beyond 7500 limit.
        counters_limit = 7500

        counters = sorted(self.ps_counter_map.keys())

        # The number of long running commands needed to get data for all
        # counters of the device equals to floor division of the current
        # counters_line length by the calculated limit, incremented by 1.
        self.num_commands = len(format_counters(counters)) // counters_limit + 1
        LOG.debug('Creating {0} long running command(s)'.format(
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
            SOURCETYPE,
            )

    @classmethod
    def params(cls, datasource, context):
        counter = datasource.talesEval(datasource.counter, context)
        if getattr(context, 'perfmonInstance', None):
            counter = ''.join((context.perfmonInstance, counter))

        return {'counter': counter}

    @defer.inlineCallbacks
    def collect(self, config):
        '''
        Collect for config.

        Called each collection interval.
        '''
        yield self.start()

        data = yield self.get_data()
        defer.returnValue(data)

    @defer.inlineCallbacks
    def start(self):
        '''
        Start the continuous command.
        '''
        if self.state != PluginStates.STOPPED:
            defer.returnValue(None)

        LOG.debug("starting Get-Counter on %s", self.config.id)
        self.state = PluginStates.STARTING

        try:
            yield self.complex_command.start(self.commandlines)
        except Exception as e:
            LOG.warn(
                "Error on %s: %s",
                self.config.id,
                e.message or "timeout")

            self._errorMsgCheck(e.message)

            self.state = PluginStates.STOPPED
            defer.returnValue(None)
        else:
            self._generateClearAuthEvents()

        self.state = PluginStates.STARTED
        self.collected_samples = 0
        self.collected_counters = set()

        self.receive()

        # When running in the foreground without the --cycle option we
        # must wait for the receive deferred to fire to have any chance
        # at collecting data.
        if not self.cycling:
            yield self.receive_deferreds

        defer.returnValue(None)

    @defer.inlineCallbacks
    def get_data(self):
        '''
        Wait for data to arrive if necessary, then return it.
        '''
        data = PERSISTER.pop(self.config.id)
        if data and data['values']:
            defer.returnValue(data)
        if data and data['events']:
            for evt in data['events']:
                PERSISTER.add_event(self.config.id, evt)

        if hasattr(self, '_wait_for_data'):
            LOG.debug("waiting for %s Get-Counter data", self.config.id)
            self.data_deferred = defer.Deferred()
            try:
                yield add_timeout(self.data_deferred, self.sample_interval)
            except Exception:
                pass
        else:
            self._wait_for_data = True

        defer.returnValue(PERSISTER.pop(self.config.id))

    @defer.inlineCallbacks
    def stop(self):
        '''
        Stop the continuous command.
        '''
        if self.state != PluginStates.STARTED:
            LOG.debug(
                "skipping Get-Counter stop on %s while it's %s",
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
            except Exception, ex:
                if 'canceled by the user' in ex.message:
                    # This means the command finished naturally before
                    # we got a chance to stop it. Totally normal.
                    log_level = logging.DEBUG
                else:
                    # Otherwise this could result in leaking active
                    # operations on the Windows server and should be
                    # logged as a warning.
                    log_level = logging.WARN

                LOG.log(
                    log_level,
                    "failed to stop Get-Counter on %s: %s",
                    self.config.id, ex)

        self.state = PluginStates.STOPPED

        defer.returnValue(None)

    @defer.inlineCallbacks
    def restart(self):
        '''
        Stop then start the long-running command.
        '''
        yield self.stop()
        yield self.start()
        defer.returnValue(None)

    def receive(self):
        '''
        Receive results from continuous command.
        '''
        deferreds = []
        for cmd in self.complex_command.commands:
            try:
                deferreds.append(cmd.receive())
            except Exception as err:
                LOG.error('Receive error {0}'.format(err))

        self.receive_deferreds = add_timeout(
            defer.DeferredList(deferreds, consumeErrors=True),
            OPERATION_TIMEOUT + 5)

        self.receive_deferreds.addCallbacks(
            self.onReceive, self.onReceiveFail)

    def _parse_deferred_result(self, result):
        '''
        Group all stdout data and failures from each command result
        and return them as a tuple of two lists: (filures, results)
        '''
        failures, results = [], []

        for index, command_result in enumerate(result):
            # The DeferredList result is of type:
            # [(True/False, [stdout, stderr]/failure), ]
            success, data = command_result
            if success:
                stdout, stderr = data
                # Log error message if present.
                if stderr:
                    LOG.debug(' '.join(stderr))
                # Leave sample start marker in first command result
                # to properly report missing counters.
                if index == 0:
                    results.extend(stdout)
                else:
                    results.extend(format_stdout(stdout)[0])
            else:
                failures.append(data)

        return failures, results

    @defer.inlineCallbacks
    def onReceive(self, result):
        # Group the result of all commands into a single result.
        failures, results = self._parse_deferred_result(result)

        collect_time = int(time.time())

        # Initialize sample buffer. Start of a new sample.
        stdout_lines, sample_start = format_stdout(results)

        if stdout_lines:
            LOG.debug("received Get-Counter data for %s", self.config.id)
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
                    self.sample_buffer.popleft().strip(' :').split('\\', 3)[3])

                value = self.sample_buffer.popleft()

                # ZEN-12024: Some locales use ',' as the decimal point.
                if ',' in value:
                    value = value.replace(',', '.', 1)

                component, datasource, event_class = self.counter_map.get(counter, (None, None, None))
                if datasource:
                    self.collected_counters.add(counter)

                    # We special-case the sysUpTime datapoint to convert
                    # from seconds to centi-seconds. Due to its origin in
                    # SNMP monitor Zenoss expects uptime in centi-seconds
                    # in many places.
                    if datasource == 'sysUpTime' and value is not None:
                        value = float(value) * 100

                    PERSISTER.add_value(
                        self.config.id, component, datasource, value, collect_time)
            except Exception, err:
                LOG.debug('Could not process a sample. Error: {}'.format(err))

        if self.data_deferred and not self.data_deferred.called:
            self.data_deferred.callback(None)

        # Report missing counters every sample interval.
        if self.collected_counters and self.collected_samples >= self.max_samples:
            self.reportMissingCounters(
                self.counter_map, self.collected_counters)
            # Reinitialize collected counters for reporting.
            self.collected_counters = set()

        # Log error message and wait for the data.
        if failures and not results:
            # No need to call onReceiveFail for each command in DeferredList.
            self.onReceiveFail(failures[0])

        # Continue to receive if MaxSamples value has not been reached yet.
        elif self.collected_samples < self.max_samples and results:
            self.receive()

        # In case ZEN-12676/ZEN-11912 are valid issues.
        elif not results and not failures and self.cycling:
            try:
                yield self.remove_corrupt_counters()
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
                LOG.debug('Result: {0}'.format(result))
                yield self.restart()

        self._generateClearAuthEvents()

        defer.returnValue(None)

    @defer.inlineCallbacks
    def onReceiveFail(self, failure):
        e = failure.value

        if isinstance(e, defer.CancelledError):
            return

        retry, level, msg = (False, None, None)  # NOT USED.

        self._errorMsgCheck(e.message)

        # Handle errors on which we should retry the receive.
        if 'OperationTimeout' in e.message:
            retry, level, msg = (
                True,
                logging.DEBUG,
                "OperationTimeout on {}"
                .format(self.config.id))

        elif isinstance(e, ConnectError):
            retry, level, msg = (
                isinstance(e, TimeoutError),
                logging.WARN,
                "network error on {}: {}"
                .format(self.config.id, e.message or 'timeout'))
            if isinstance(e, TimeoutError):
                self.network_failures += 1
        # Handle errors on which we should start over.
        else:
            retry, level, msg = (
                False,
                logging.WARN,
                "receive failure on {}: {}"
                .format(self.config.id, e))

        if self.data_deferred and not self.data_deferred.called:
            self.data_deferred.errback(failure)

        LOG.log(level, msg)
        if self.network_failures >= MAX_NETWORK_FAILURES:
            yield self.stop()
            self.reset()
        if retry:
            self.receive()
        else:
            yield self.restart()

        defer.returnValue(None)

    @defer.inlineCallbacks
    def search_corrupt_counters(self, winrs, counter_list, corrupt_list):
        '''
        Bisect the counters to determine which of them are corrupt.
        '''
        command = lambda counters: (
            "powershell -NoLogo -NonInteractive -NoProfile -Command "
            "\"get-counter -counter @({0})\" ".format(
                ', '.join("('{0}')".format(c) for c in counters))
        )

        num_counters = len(counter_list)

        if num_counters == 0:
            pass
        elif num_counters == 1:
            result = yield winrs.run_command(command(counter_list))
            if result.stderr:
                corrupt_list.extend(counter_list)
        else:
            mid_index = num_counters/2
            slices = (counter_list[:mid_index], counter_list[mid_index:])
            for counter_slice in slices:
                result = yield winrs.run_command(command(counter_slice))
                if result.stderr:
                    yield self.search_corrupt_counters(
                        winrs, counter_slice, corrupt_list)

        defer.returnValue(corrupt_list)

    @defer.inlineCallbacks
    def remove_corrupt_counters(self):
        '''
        Remove counters which return an error.
        '''
        LOG.debug('Performing check for corrupt counters')
        dsconf0 = self.config.datasources[0]
        winrs = create_single_shot_command(createConnectionInfo(dsconf0))

        counter_list = sorted(
            set(self.ps_counter_map.keys())-set(CORRUPT_COUNTERS[dsconf0.device]))
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
        '''
        Emit event for corrupt counters
        '''
        default_eventClass = '/Status/Winrm'
        dsconf0 = self.config.datasources[0]

        events = {}
        for req_counter in requested:
            if req_counter in CORRUPT_COUNTERS[dsconf0.device]:
                component, datasource, event_class = requested.get(req_counter, (None, None, None))
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
                PERSISTER.add_event(self.config.id, {
                    'device': self.config.id,
                    'severity': ZenEventClasses.Error,
                    'eventClass': event,
                    'eventKey': 'Windows Perfmon Corrupt Counters',
                    'summary': self.corrupt_counters_summary(len(events[event])),
                    'corrupt_counters': self.missing_counters_str(events[event]).decode('UTF-8'),
                })

        for req_counter in requested:
            component, datasource, event_class = requested.get(req_counter, (None, None, None))
            event_class = event_class or default_eventClass
            if event_class not in events:
                PERSISTER.add_event(self.config.id, {
                    'device': self.config.id,
                    'severity': ZenEventClasses.Clear,
                    'eventClass': event_class or default_eventClass,
                    'eventKey': 'Windows Perfmon Corrupt Counters',
                    'summary': '0 counters corrupt in collection',
                })

    def reportMissingCounters(self, requested, returned):
        '''
        Emit logs and events for counters requested but not returned.
        '''
        missing_counters = set(requested).difference(returned)
        default_eventClass = '/Status/Winrm'

        events = {}
        for req_counter in requested:
            if req_counter in missing_counters:
                component, datasource, event_class = requested.get(req_counter, (None, None, None))
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
                PERSISTER.add_event(self.config.id, {
                    'device': self.config.id,
                    'severity': ZenEventClasses.Info,
                    'eventClass': event,
                    'eventKey': 'Windows Perfmon Missing Counters',
                    'summary': self.missing_counters_summary(len(events[event])),
                    'missing_counters': self.missing_counters_str(events[event]).decode('UTF-8'),
                })

        for req_counter in requested:
            component, datasource, event_class = requested.get(req_counter, (None, None, None))
            event_class = event_class or default_eventClass
            if event_class not in events:
                PERSISTER.add_event(self.config.id, {
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
        '''
        Cleanup any resources associated with this task.

        This can happen when zenpython terminates, or anytime config is
        deleted or modified.
        '''
        return reactor.callLater(self.sample_interval, self.stop)

    def _errorMsgCheck(self, errorMessage):
        """Check error message and generate appropriate event."""
        if 'Password expired' in errorMessage:
            PERSISTER.add_event(self.config.id, {
                'device': self.config.id,
                'severity': ZenEventClasses.Critical,
                'eventClassKey': 'MW|PasswordExpired',
                'summary': errorMessage,
                'ipAddress': self.config.manageIp})
        elif 'Check username and password' in errorMessage:
            PERSISTER.add_event(self.config.id, {
                'device': self.config.id,
                'severity': ZenEventClasses.Critical,
                'eventClassKey': 'MW|WrongCredentials',
                'summary': errorMessage,
                'ipAddress': self.config.manageIp})

    def _generateClearAuthEvents(self):
        """Add clear authentication events to PERSISTER singleton."""
        PERSISTER.add_event(self.config.id, {
            'eventClass': '/Status/Winrm/Auth/PasswordExpired',
            'device': self.config.id,
            'severity': ZenEventClasses.Clear,
            'eventClassKey': 'MW|PasswordExpired',
            'summary': 'Password is not expired',
            'ipAddress': self.config.manageIp})
        PERSISTER.add_event(self.config.id, {
            'eventClass': '/Status/Winrm/Auth/WrongCredentials',
            'device': self.config.id,
            'severity': ZenEventClasses.Clear,
            'eventClassKey': 'MW|WrongCredentials',
            'summary': 'Credentials are OK',
            'ipAddress': self.config.manageIp})


# Helper functions for PerfmonDataSource plugin.
def convert_to_ps_counter(counter):
    esc_counter = counter.encode("unicode_escape")
    start_indx = esc_counter.find('(')
    end_indx = esc_counter.rfind(')')
    resource = esc_counter[start_indx + 1:end_indx]
    if '\u' in resource and start_indx != -1 and end_indx != -1:
        ps_repr = resource.replace('\u', '+[char]0x')
        ps_counter = [esc_counter[:start_indx]]
        ps_counter.append("('")
        ps_counter.append(ps_repr)
        ps_counter.append("+'")
        ps_counter.append(esc_counter[end_indx:])
        return ''.join(ps_counter).decode('string_escape')
    return counter


def format_counters(ps_counters):
    '''
    Convert a list of supplied counters into a string, which will
    be further used to cteate ps command line.
    '''
    return ','.join(
        "('{0}')".format(counter) for counter in ps_counters)


def chunkify(lst, n):
    '''
    Yield successive n-sized chunks from the list.
    '''
    return [lst[i::n] for i in xrange(n)]


def format_stdout(stdout_lines):
    '''
    Return a tuple containing a list of stdout lines without the
    BOM marker and property name, and a bool value specifying if it
    is a start of a sample.
    '''
    sample_start = False
    # Remove BOM marker(if present).
    if stdout_lines and stdout_lines[0] == unicode(codecs.BOM_UTF8, "utf8"):
        stdout_lines = stdout_lines[1:]

    # Remove property name from the first stdout line.
    if stdout_lines and stdout_lines[0].startswith('Readings : '):
        stdout_lines[0] = stdout_lines[0].replace('Readings : ', '', 1)
        sample_start = True

    return stdout_lines, sample_start
