##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
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
LOG = logging.getLogger('zen.windows')

import collections
import time

from twisted.internet import defer
from twisted.internet.error import ConnectError, TimeoutError

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

from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath
from ZenPacks.zenoss.Microsoft.Windows.twisted_utils import add_timeout, sleep

addLocalLibPath()

from txwinrm.util import ConnectionInfo
from txwinrm.shell import create_long_running_command


ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
SOURCETYPE = 'Windows Perfmon'

# This should match OperationTimeout in txwinrm's receive.xml.
OPERATION_TIMEOUT = 60


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


class PerfmonDataSourcePlugin(PythonDataSourcePlugin):
    proxy_attributes = (
        'zWinRMUser',
        'zWinRMPassword',
        'zWinRMPort',
        'zWinKDC',
        'zWinKeyTabFilePath',
        'zWinScheme',
        )

    config = None
    cycling = None
    initialized = None
    state = None
    last_time = None
    receive_deferred = None
    data_deferred = None
    command = None
    data = None
    sample_interval = None
    sample_buffer = []
    max_samples = None
    collected_samples = None
    counter_map = None

    def __init__(self):
        self.initialized = False
        self.state = PluginStates.STOPPED
        self.data = self.new_data()

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

        return {
            'counter': counter,
            }

    def initialize(self, config):
        '''
        Initialize the task.

        Only logic that should only ever be executed as single time when
        a task is created should go here.
        '''
        dsconf0 = config.datasources[0]

        scheme = dsconf0.zWinScheme
        port = int(dsconf0.zWinRMPort)
        auth_type = 'kerberos' if '@' in dsconf0.zWinRMUser else 'basic'
        connectiontype = 'Keep-Alive'
        keytab = dsconf0.zWinKeyTabFilePath
        dcip = dsconf0.zWinKDC

        preferences = queryUtility(ICollectorPreferences, 'zenpython')
        self.cycling = preferences.options.cycle

        if self.cycling:
            self.sample_interval = dsconf0.cycletime
            self.max_samples = max(600 / self.sample_interval, 1)
        else:
            self.sample_interval = 1
            self.max_samples = 1

        self.counter_map = {}
        for dsconf in config.datasources:
            self.counter_map[dsconf.params['counter'].lower()] = (
                dsconf.component,
                dsconf.datasource,
                )

        self.commandline = (
            'powershell -NoLogo -NonInteractive -NoProfile -Command "'
            '$FormatEnumerationLimit = -1 ; '
            '$Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size (4096, 25) ; '
            'get-counter -ea silentlycontinue '
            '-SampleInterval {SampleInterval} -MaxSamples {MaxSamples} '
            '-counter @({Counters}) '
            '| Format-List -Property Readings"'
            ).format(
            SampleInterval=self.sample_interval,
            MaxSamples=self.max_samples,
            Counters=', '.join("'{0}'".format(c) for c in self.counter_map),
            )

        self.config = config
        try:
            self.command = create_long_running_command(
                ConnectionInfo(
                    dsconf0.manageIp,
                    auth_type,
                    dsconf0.zWinRMUser,
                    dsconf0.zWinRMPassword,
                    scheme,
                    port,
                    connectiontype,
                    keytab,
                    dcip))
        except Exception, e:
            self.initialized = False
            LOG.warn(
                "Connection error on %s: %s",
                self.config.id,
                e.message.capitalize() or "the task is not Initialized"
            )
            return
        self.initialized = True

    @defer.inlineCallbacks
    def collect(self, config):
        '''
        Collect for config.

        Called each collection interval.
        '''
        if not self.initialized:
            self.initialize(config)
        if self.initialized:
            yield self.start()
        yield self.wait_for_data()

        # Reset so we don't deliver the same results more than once.
        data = self.data.copy()
        self.data = self.new_data()

        defer.returnValue(data)

    @defer.inlineCallbacks
    def wait_for_data(self):
        '''
        Wait for no more than 5 seconds for data to be received.

        When we ask for data, we know that we won't get the data back
        until now + cycletime. This introduces a race condition on the
        next collection interval where the data won't yet be available
        for a fraction of a second. This means we have to wait another
        collection interval before the data will be available.

        We can try to predict if we're going to get data soon based on
        when we last asked for, or received, data. If "soon" is soon
        enough, we'll sleep to wait for the data.
        '''
        if self.last_time:
            until_time = self.sample_interval - (time.time() - self.last_time)

            if until_time <= 0:
                defer.returnValue(None)

            wait_time = until_time + 2
            if wait_time < min(5, self.sample_interval):
                LOG.debug(
                    "waiting %.2f seconds for %s Get-Counter data",
                    wait_time, self.config.id)

                self.data_deferred = defer.Deferred()
                try:
                    yield add_timeout(self.data_deferred, wait_time)
                except Exception:
                    pass

        defer.returnValue(None)

    @defer.inlineCallbacks
    def start(self):
        '''
        Start the continuous command.
        '''
        if self.state != PluginStates.STOPPED:
            LOG.debug(
                "skipping Get-Counter start on %s while it's %s",
                self.config.id,
                self.state)

            defer.returnValue(None)

        LOG.debug("starting Get-Counter on %s", self.config.id)
        self.state = PluginStates.STARTING

        try:
            yield self.command.start(self.commandline)
        except Exception as e:
            LOG.warn(
                "Error on %s: %s",
                self.config.id,
                e.message or "timeout")

            self.state = PluginStates.STOPPED
            defer.returnValue(None)

        self.state = PluginStates.STARTED
        self.last_time = time.time()
        self.collected_samples = 0
        self.collected_counters = set()

        self.receive()

        # When running in the foreground without the --cycle option we
        # must wait for the receive deferred to fire to have any chance
        # at collecting data.
        if not self.cycling:
            yield self.receive_deferred

        defer.returnValue(None)

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

        if self.receive_deferred:
            try:
                self.receive_deferred.cancel()
            except Exception:
                pass

        if self.command:
            try:
                yield self.command.stop()
            except Exception, ex:
                # Log this as a warning because it can mean that a WSMan
                # active operation has been leaked on the Windows
                # server.
                LOG.warn(
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
        self.receive_deferred = add_timeout(
            self.command.receive(), OPERATION_TIMEOUT + 5)

        self.receive_deferred.addCallbacks(
            self.onReceive, self.onReceiveFail)

    @defer.inlineCallbacks
    def onReceive(self, result):
        self.last_time = time.time()

        # Initialize sample buffer. Start of a new sample.
        stdout_lines = result[0]
        if stdout_lines:
            if stdout_lines[0].startswith('Readings : '):
                stdout_lines[0] = stdout_lines[0].replace('Readings : ', '', 1)

                if self.collected_counters:
                    self.reportMissingCounters(
                        self.counter_map, self.collected_counters)

                self.sample_buffer = collections.deque(stdout_lines)
                self.collected_counters = set()
                self.collected_samples += 1

            # Extend sample buffer. Continuation of previous sample.
            else:
                self.sample_buffer.extend(stdout_lines)

        # Continue while we have counter/value pairs.
        while len(self.sample_buffer) > 1:
            # Buffer to counter conversion:
            #   '\\\\amazona-q2r281f\\web service(another web site)\\move requests/sec :'
            #   '\\\\amazona-q2r281f\\web service(another web site)\\move requests/sec'
            #   '\\web service(another web site)\\move requests/sec'
            counter = '\\{}'.format(
                self.sample_buffer.popleft().strip(' :').split('\\', 3)[3])

            value = float(self.sample_buffer.popleft())

            component, datasource = self.counter_map.get(counter, (None, None))
            if datasource:
                self.collected_counters.add(counter)

                # We special-case the sysUpTime datapoint to convert
                # from seconds to centi-seconds. Due to its origin in
                # SNMP monitor Zenoss expects uptime in centi-seconds
                # in many places.
                if datasource == 'sysUpTime' and value is not None:
                    value = float(value) * 100

                self.data['values'][component][datasource] = (
                    value, int(self.last_time))

        LOG.debug("received Get-Counter data for %s", self.config.id)

        if self.data_deferred and not self.data_deferred.called:
            self.data_deferred.callback(None)

        if self.collected_samples < self.max_samples and result[0]:
            self.receive()
        else:
            if self.cycling:
                yield self.restart()

        defer.returnValue(None)

    @defer.inlineCallbacks
    def onReceiveFail(self, failure):
        e = failure.value

        if isinstance(e, defer.CancelledError):
            return

        retry, level, msg = (False, None, None)

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

        # Handle errors on which we should start over.
        else:
            retry, level, msg = (
                False,
                logging.WARN,
                "receive failure on {}: {}"
                .format(self.config.id, failure))

        if self.data_deferred and not self.data_deferred.called:
            self.data_deferred.errback(failure)

        LOG.log(level, msg)
        if retry:
            self.receive()
        else:
            yield self.restart()

        defer.returnValue(None)

    def reportMissingCounters(self, requested, returned):
        '''
        Emit logs and events for counters requested but not returned.
        '''
        missing_counters = set(requested).difference(returned)
        if missing_counters:
            missing_counter_count = len(missing_counters)

            LOG.warn(
                "%s missing counters for %s - see debug for details",
                missing_counter_count,
                self.config.id)

            missing_counters_str = ', '.join(missing_counters)

            LOG.debug(
                "%s missing counters for %s: %s",
                missing_counter_count,
                self.config.id,
                missing_counters_str)

            summary = (
                '{} counters missing in collection - see details'
                .format(missing_counter_count))

            self.data['events'].append({
                'device': self.config.id,
                'severity': ZenEventClasses.Info,
                'eventKey': 'Windows Perfmon Missing Counters',
                'summary': summary,
                'missing_counters': missing_counters_str,
                })
        else:
            self.data['events'].append({
                'device': self.config.id,
                'severity': ZenEventClasses.Clear,
                'eventKey': 'Windows Perfmon Missing Counters',
                'summary': '0 counters missing in collection',
                })

    def cleanup(self, config):
        '''
        Cleanup any resources associated with this task.

        This can happen when zenpython terminates, or anytime config is
        deleted or modified.
        '''
        return self.stop()
