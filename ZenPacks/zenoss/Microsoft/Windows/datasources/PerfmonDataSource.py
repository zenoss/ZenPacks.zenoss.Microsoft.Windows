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
from ZenPacks.zenoss.Microsoft.Windows.twisted_utils import add_timeout

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
    started = None
    receive_deferred = None
    command = None
    data = None
    sample_interval = None
    max_samples = None
    collected_samples = None
    counter_map = None

    def __init__(self):
        self.initialized = False
        self.started = False
        self.data = self.new_data()

    @classmethod
    def config_key(cls, datasource, context):
        return (
            context.device().id,
            datasource.getCycleTime(context),
            )

    @classmethod
    def params(cls, datasource, context):
        counter = datasource.talesEval(datasource.counter, context)
        if getattr(context, 'perfmonInstance', None):
            counter = ''.join((context.perfmonInstance, counter))

        return {
            'counter': counter,
            }

    @defer.inlineCallbacks
    def collect(self, config):
        '''
        Collect for config.

        Called each collection interval.
        '''
        if not self.initialized:
            self.initialize(config)

        if not self.started:
            yield self.start()

        # Reset so we don't deliver the same results more than once.
        data = self.data.copy()
        self.data = self.new_data()

        defer.returnValue(data)

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
            self.max_samples = 600 / self.sample_interval
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

        self.initialized = True

    @defer.inlineCallbacks
    def start(self):
        '''
        Start the continuous command.
        '''
        try:
            yield self.command.start(self.commandline)
        except ConnectError as e:
            LOG.warn(
                "Connection error on %s: %s",
                self.config.id,
                e.message or "timeout")

            self.started = False
            defer.returnValue(None)

        self.started = True
        self.collected_samples = 0
        self.collected_counters = set()

        self.receive()

        if not self.cycling:
            yield self.receive_deferred

        defer.returnValue(None)

    @defer.inlineCallbacks
    def stop(self):
        '''
        Stop the continuous command.
        '''
        LOG.debug("stopping Get-Counter on %s", self.config.id)

        self.started = False

        if self.receive_deferred:
            try:
                self.receive_deferred.cancel()
            except Exception:
                pass

        if self.command:
            try:
                yield self.command.stop()
            except Exception, ex:
                LOG.debug(
                    "failed to stop Get-Counter on %s: %s",
                    self.config.id, ex)

        defer.returnValue(None)

    def receive(self):
        '''
        Receive results from continuous command.
        '''
        self.receive_deferred = add_timeout(
            self.command.receive(), OPERATION_TIMEOUT + 5)

        self.receive_deferred.addCallbacks(
            self.onReceive, self.onReceiveFail)

    def onReceive(self, result):
        receive_time = int(time.time())

        # Initialize sample buffer. Start of a new sample.
        if result[0][0].startswith('Readings : '):
            result[0][0] = result[0][0].replace('Readings : ', '', 1)

            if self.collected_counters:
                self.reportMissingCounters(
                    self.counter_map, self.collected_counters)

            self.sample_buffer = collections.deque(result[0])
            self.collected_counters = set()
            self.collected_samples += 1

        # Extend sample buffer. Continuation of previous sample.
        else:
            self.sample_buffer.extend(result[0])

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

                self.data['values'][component][datasource] = (value, receive_time)

        if self.collected_samples < self.max_samples and result[0]:
            self.receive()
        else:
            if self.cycling:
                self.start()

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

        LOG.log(level, msg)
        if retry:
            self.receive()
        else:
            self.start()

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

            LOG.debug(
                "%s missing counters for %s: %s",
                missing_counter_count,
                self.config.id,
                ', '.join(missing_counters))

            summary = (
                '{} counters missing in collection - see details'
                .format(missing_counter_count))

            message = (
                '{} counters missing in collection: {}'
                .format(
                    missing_counter_count,
                    ', '.join(missing_counters)))

            self.data['events'].append({
                'device': self.config.id,
                'severity': ZenEventClasses.Info,
                'component': 'Perfmon',
                'eventKey': 'Windows Perfmon Missing Counters',
                'summary': summary,
                'message': message,
                })
        else:
            self.data['events'].append({
                'device': self.config.id,
                'severity': ZenEventClasses.Clear,
                'component': 'Perfmon',
                'eventKey': 'Windows Perfmon Missing Counters',
                'summary': '0 counters missing in collection',
                })

    def cleanup(self, config):
        '''
        Cleanup any resources associated with this task.

        This can happen when zenpython terminates, or anytime config is
        deleted or modified.
        '''
        if self.config:
            return self.stop()

        return defer.succeed(None)
