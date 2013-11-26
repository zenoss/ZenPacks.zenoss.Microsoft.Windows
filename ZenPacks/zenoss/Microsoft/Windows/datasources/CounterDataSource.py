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

import itertools
import time

from twisted.internet import defer
from twisted.python.failure import Failure

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

addLocalLibPath()

from txwinrm.util import ConnectionInfo
from txwinrm.shell import create_long_running_command


ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
SOURCETYPE = 'Windows Perfmon'


class CounterDataSource(PythonDataSource):
    ZENPACKID = ZENPACKID

    sourcetype = SOURCETYPE
    sourcetypes = (SOURCETYPE,)

    plugin_classname = (
        ZENPACKID + '.datasources.CounterDataSource.CounterDataSourcePlugin')

    # Defaults for PythonDataSource user-facing properties.
    cycletime = '${here/zWinPerfmonInterval}'

    # Defaults for local user-facing properties.
    counter = ''

    _properties = PythonDataSource._properties + (
        {'id': 'counter', 'type': 'string'},
        )


class ICounterDataSourceInfo(IRRDDataSourceInfo):
    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    counter = schema.TextLine(
        group=_t(SOURCETYPE),
        title=_t('Counter'))


class CounterDataSourceInfo(RRDDataSourceInfo):
    implements(ICounterDataSourceInfo)
    adapts(CounterDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    counter = ProxyProperty('counter')


def group(lst, n):
    """group([0,3,4,10,2,3], 2) => iterator

    Group an iterable into an n-tuples iterable. Incomplete tuples
    are discarded e.g.

    >>> list(group(range(10), 3))
    [(0, 1, 2), (3, 4, 5), (6, 7, 8)]
    """
    return itertools.izip(*[itertools.islice(lst, i, None, n) for i in range(n)])


class CounterDataSourcePlugin(PythonDataSourcePlugin):
    proxy_attributes = (
        'zWinUser',
        'zWinPassword',
        'zWinRMPort',
        'zWinKDC',
        'zWinKeyTabFilePath',
        'zWinScheme',
        )

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

        if self.data:
            data = self.data.copy()

            # Reset so we don't deliver the same results more than once.
            self.data = None
        else:
            data = self.new_data()

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
        auth_type = 'kerberos' if '@' in dsconf0.zWinUser else 'basic'
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

        self.connection_info = ConnectionInfo(
            dsconf0.manageIp,
            auth_type,
            dsconf0.zWinUser,
            dsconf0.zWinPassword,
            scheme,
            port,
            connectiontype,
            keytab,
            dcip)

        self.command = create_long_running_command(self.connection_info)

        self.initialized = True

    @defer.inlineCallbacks
    def start(self):
        '''
        Start the continuous command.
        '''
        yield self.command.start(self.commandline)

        self.started = True
        self.collected_samples = 0

        self.receive()

        if not self.cycling:
            yield self.receive_deferred

        defer.returnValue(None)

    def receive(self):
        '''
        Receive results from continuous command.
        '''
        self.receive_deferred = self.command.receive()
        self.receive_deferred.addCallbacks(
            self.onReceive, self.onReceiveFail)

    def onReceive(self, result):
        receive_time = time.time()

        self.data = self.new_data()

        collected_counters = set()

        for label, value in group(result[0], 2):
            fq_counter = label.strip(' :').split(' : ')[-1]
            counter = '\\{}'.format(fq_counter.split('\\', 3)[3])

            collected_counters.add(counter)

            component, datasource = self.counter_map.get(counter, (None, None))
            if not datasource:
                continue

            self.data['values'][component][datasource] = (value, receive_time)

        unexpected_counters = collected_counters.difference(self.counter_map)
        if unexpected_counters:
            LOG.warn(
                "unexpected counters for %s: %s",
                self.config.id,
                ', '.join(unexpected_counters))

        missing_counters = set(self.counter_map).difference(collected_counters)
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

        self.collected_samples += 1
        if self.collected_samples < self.max_samples and result[0]:
            self.receive()
        else:
            if self.cycling:
                self.start()

    def onReceiveFail(self, failure):
        if isinstance(failure.value, defer.CancelledError):
            return

        if 'OperationTimeout' in failure.value.message:
            LOG.debug(
                "%s failed to return output within OperationTimeout",
                self.config.id)

            self.receive()
        else:
            LOG.error(
                "%s failed to return output: %s",
                self.config.id,
                failure)

            self.start()

    @defer.inlineCallbacks
    def cleanup(self, config):
        '''
        Cleanup any resources associated with this task.

        This can happen when zenpython terminates, or anytime config is
        deleted or modified.
        '''
        LOG.debug("stopping Get-Counter on %s", config.id)

        if self.receive_deferred:
            self.receive_deferred.cancel()

        if self.command:
            try:
                yield self.command.stop()
            except Exception, ex:
                LOG.debug(
                    "failed to stop Get-Counter on %s: %s",
                    config.id, ex)

        self.started = False
        self.command = None
        self.data = None

        defer.returnValue(None)
