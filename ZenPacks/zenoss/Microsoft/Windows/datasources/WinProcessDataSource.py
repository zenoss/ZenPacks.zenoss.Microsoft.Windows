##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
A datasource that uses WinRM to monitor Windows process status and
performance.
'''

import logging
LOG = logging.getLogger('zen.WindowsProcess')

import collections
import re

from zope.component import adapts
from zope.interface import implements

from Products.ZenEvents import Event
from Products.ZenEvents.ZenEventClasses import Status_OSProcess
from Products.ZenModel.OSProcess import OSProcess
from Products.Zuul.form import schema
from Products.Zuul.infos import InfoBase, ProxyProperty
from Products.Zuul.interfaces import IInfo
from Products.Zuul.utils import ZuulMessageFactory as _t

from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin

from ZenPacks.zenoss.Microsoft.Windows import ZENPACK_NAME
from ZenPacks.zenoss.Microsoft.Windows.utils import (
    addLocalLibPath,
    get_processText,
    )

addLocalLibPath()

import txwinrm.collect


SOURCE_TYPE = 'Windows Process'

# Win32_PerfFormattedData_PerfProc_Process attributes that are valid
# datapoints. This is used to prevent the user from creating invalid
# datapoints that the query and therefore collection.
VALID_DATAPOINTS = frozenset({
    'CreatingProcessID',
    'ElapsedTime',
    'Frequency_Object',
    'Frequency_PerfTime',
    'Frequency_Sys100NS',
    'HandleCount',
    'IDProcess',
    'IODataBytesPerSec',
    'IODataOperationsPerSec',
    'IOOtherBytesPerSec',
    'IOOtherOperationsPerSec',
    'IOReadBytesPerSec',
    'IOReadOperationsPerSec',
    'IOWriteBytesPerSec',
    'IOWriteOperationsPerSec',
    'PageFaultsPerSec',
    'PageFileBytes',
    'PageFileBytesPeak',
    'PercentPrivilegedTime',
    'PercentProcessorTime',
    'PercentUserTime',
    'PoolNonpagedBytes',
    'PoolPagedBytes',
    'PriorityBase',
    'PrivateBytes',
    'ThreadCount',
    'Timestamp_Object',
    'Timestamp_PerfTime',
    'Timestamp_Sys100NS',
    'VirtualBytes',
    'VirtualBytesPeak',
    'WorkingSet',
    'WorkingSetPeak',
    })

# Win32_PerfFormattedData_PerfProc_Process attributes that we don't
# want to aggregate when multiple processes are found to match a single
# Zenoss OSProcess. Any other numeric datapoints will be summed.
NON_AGGREGATED_DATAPOINTS = frozenset({
    'CreatingProcessID',
    'IDProcess',
    'PriorityBase',
    })

COUNT_DATAPOINT = 'count'

# Process monitoring changed significantly in Zenoss 4.2.4. We want to
# support the new and old ways.
NEW_STYLE = hasattr(OSProcess, 'processText')


class WinProcessDataSource(PythonDataSource):
    ZENPACKID = ZENPACK_NAME

    sourcetypes = (SOURCE_TYPE,)
    sourcetype = SOURCE_TYPE

    # RRDDataSource
    component = '${here/id}'
    eventClass = Status_OSProcess
    severity = Event.Critical

    # PythonDataSource
    plugin_classname = '.'.join((
        ZENPACK_NAME,
        'datasources',
        'WinProcessDataSource',
        'WinProcessDataSourcePlugin'))

    def getDescription(self):
        '''
        Return short string that represents this datasource.
        '''
        return SOURCE_TYPE

    def getCycleTime(self, context):
        '''
        Return the cycletime for this datasource given its context.

        Overridden here to use the PerformanceConf.processCycleInterval
        for consistency with other process monitoring.
        '''
        return context.perfServer().processCycleInterval


class IWinProcessDataSourceInfo(IInfo):
    '''
    Info interface for WinProcessDataSource.

    Extends IInfo instead of IRRDDataSourceInfo because we want to
    reduce the set of options available.
    '''

    newId = schema.TextLine(
        title=_t(u'Name'),
        xtype='idfield',
        description=_t(u'The name of this datasource'))

    type = schema.TextLine(
        title=_t(u'Type'),
        readonly=True)

    enabled = schema.Bool(
        title=_t(u'Enabled'))

    severity = schema.TextLine(
        title=_t(u'Severity'),
        group=_t(u'Event Information'),
        readonly=True)

    eventClass = schema.TextLine(
        title=_t(u'Event Class'),
        group=_t(u'Event Information'),
        readonly=True)

    component = schema.TextLine(
        title=_t(u'Component'),
        group=_t(u'Event Information'),
        readonly=True)


class WinProcessDataSourceInfo(InfoBase):
    '''
    Info adapter factory for WinProcessDataSource.

    Extends InfoBase instead of RRDDataSourceInfo because we want to
    reduce the set of options available.
    '''

    implements(IWinProcessDataSourceInfo)
    adapts(WinProcessDataSource)

    enabled = ProxyProperty('enabled')

    severity = 'Process fail severity setting.'
    eventClass = Status_OSProcess
    component = 'Process.'

    @property
    def id(self):
        return '/'.join(self._object.getPrimaryPath())

    @property
    def newId(self):
        return self._object.id

    @property
    def source(self):
        return self._object.getDescription()

    @property
    def type(self):
        return self._object.sourcetype


class WinProcessDataSourcePlugin(PythonDataSourcePlugin):
    '''
    Collects Windows process data.
    '''

    proxy_attributes = [
        'zWinUser',
        'zWinPassword',
        'zWinRMPort',
        ]

    @classmethod
    def params(cls, datasource, context):
        process_class = context.osProcessClass()
        params = {
            'regex': process_class.regex,
            'alertOnRestart': context.alertOnRestart(),
            'severity': context.getFailSeverity(),
            }

        if NEW_STYLE:
            params['excludeRegex'] = process_class.excludeRegex
        else:
            params['ignoreParameters'] = getattr(
                process_class, 'ignoreParameters', False)

        return params

    def collect(self, config):
        ds0 = config.datasources[0]

        client = txwinrm.collect.WinrmCollectClient()
        conn_info = txwinrm.collect.ConnectionInfo(
            config.manageIp,
            'kerberos' if '@' in ds0.zWinUser else 'basic',
            ds0.zWinUser,
            ds0.zWinPassword,
            'http',
            int(ds0.zWinRMPort),
            'Keep-Alive',
            '')

        # Always query Win32_Process. This is where we get process
        # status and count.
        queries = [
            'SELECT Name, ExecutablePath, CommandLine, ProcessId '
            'FROM Win32_Process',
            ]

        # Query only for the superset of attributes needed to satisfy
        # the configured datapoints across all processes.
        perf_attrs = {p.id for s in config.datasources for p in s.points}
        if COUNT_DATAPOINT in perf_attrs:
            perf_attrs.remove(COUNT_DATAPOINT)

        # Remove invalid attributes from what we ask for. Warn the user.
        invalid_datapoints = perf_attrs.difference(VALID_DATAPOINTS)
        if invalid_datapoints:
            LOG.warn(
                "Removing invalid datapoints for %s: %s",
                config.device, ', '.join(invalid_datapoints))

            perf_attrs.remove(invalid_datapoints)

        # Only query Win32_PerfFormattedData_PerfProc_Process if its
        # necessary to satisfy the configured datapoints.
        if perf_attrs:
            queries.append(
                'SELECT IDProcess, {} '
                'FROM Win32_PerfFormattedData_PerfProc_Process'.format(
                    ', '.join(perf_attrs)))

        return client.do_collect(
            conn_info, map(txwinrm.collect.create_enum_info, queries))

    def onSuccess(self, results, config):
        data = self.new_data()

        datasource_by_pid = {}
        metrics_by_component = collections.defaultdict(
            lambda: collections.defaultdict(list))

        # Used for process restart checking.
        if not hasattr(self, 'previous_pids_by_component'):
            self.previous_pids_by_component = collections.defaultdict(set)

        pids_by_component = collections.defaultdict(set)

        # Win32_Process: Counts and correlation to performance table.
        process_key = [x for x in results if 'Win32_Process' in x.wql][0]
        for item in results[process_key]:
            processText = get_processText(item)

            for datasource in config.datasources:
                regex = re.compile(datasource.params['regex'])

                if NEW_STYLE:
                    excludeRegex = re.compile(
                        datasource.params['excludeRegex'])

                    basic_match = OSProcess.matchRegex(
                        regex, excludeRegex, processText)

                    if not basic_match:
                        continue

                    capture_match = OSProcess.matchNameCaptureGroups(
                        regex, processText, datasource.component)

                    if not capture_match:
                        continue
                else:
                    if datasource.params['ignoreParameters']:
                        processText = item.ExecutablePath or item.Name

                    if not re.search(regex, processText):
                        continue

                datasource_by_pid[item.ProcessId] = datasource
                pids_by_component[datasource.component].add(item.ProcessId)

                # Track process count. Append 1 each time we find a
                # match because the generic aggregator below will sum
                # them up to the total count.
                metrics_by_component[datasource.component][COUNT_DATAPOINT].append(1)

        # Send process status events.
        for datasource in config.datasources:
            component = datasource.component

            if COUNT_DATAPOINT in metrics_by_component[component]:
                severity = 0
                summary = 'matching processes running'

                # Process restart checking.
                previous_pids = self.previous_pids_by_component.get(component)
                current_pids = pids_by_component.get(component)

                # No restart if there are no current or previous PIDs.
                # previous PIDs.
                if not previous_pids or not current_pids:
                    continue

                # Only consider PID changes a restart if all PIDs
                # matching the process changed.
                if current_pids.isdisjoint(previous_pids):
                    summary = 'matching processes restarted'

                    # If the process is configured to alert on
                    # restart, the first "up" won't be a clear.
                    if datasource.params['alertOnRestart']:
                        severity = datasource.params['severity']

            else:
                severity = datasource.params['severity']
                summary = 'no matching processes running'

                # Add a 0 count for process that aren't running.
                metrics_by_component[component][COUNT_DATAPOINT].append(0)

            data['events'].append({
                'device': datasource.device,
                'component': component,
                'eventClass': datasource.eventClass,
                'eventGroup': 'Process',
                'summary': summary,
                'severity': severity,
                })

        # Prepare for next cycle's restart check by merging current
        # process PIDs with previous. This is to catch restarts that
        # stretch across more than subsequent cycles.
        self.previous_pids_by_component.update(
            (c, p) for c, p in pids_by_component.iteritems() if p)

        # Win32_PerfFormattedData_PerfProc_Process: Datapoints.
        perf_key = [x for x in results if 'Win32_Perf' in x.wql][0]
        for item in results[perf_key]:
            if item.IDProcess not in datasource_by_pid:
                continue

            datasource = datasource_by_pid[item.IDProcess]
            for point in datasource.points:
                if point.id == COUNT_DATAPOINT:
                    continue

                try:
                    value = int(getattr(item, point.id))
                except (TypeError, ValueError):
                    LOG.warn(
                        "%s %s %s: Couldn't convert %r to integer",
                        datasource.device, datasource.component, point.id,
                        value)
                except AttributeError:
                    LOG.warn(
                        "%s %s: %s not in result",
                        datasource.device, datasource.component, point.id)
                else:
                    metrics_by_component[datasource.component][point.id].append(value)

        # Aggregate and store datapoint values.
        for component, points in metrics_by_component.iteritems():
            for point, values in points.iteritems():
                if point in NON_AGGREGATED_DATAPOINTS:
                    value = values[0]
                else:
                    value = sum(values)

                data['values'][component][point] = (value, 'N')

        # Send overall clear.
        data['events'].append({
            'device': config.id,
            'severity': Event.Clear,
            'eventClass': Status_OSProcess,
            'summary': 'processes scan successful',
            })

        return data

    def onError(self, error, config):
        data = self.new_data()

        data['events'].append({
            'device': config.id,
            'severity': Event.Error,
            'eventClass': Status_OSProcess,
            'summary': 'processes scan error: {}'.format(error.value),
            })

        return data
