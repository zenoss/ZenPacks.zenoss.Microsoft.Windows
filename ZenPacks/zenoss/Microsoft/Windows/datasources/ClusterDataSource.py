##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2023, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that queries cluster object status.

See Products.ZenModel.ZenPack._getClassesByPath() to understand how this class
gets discovered as a datasource type in Zenoss.
"""
import time
import logging
from traceback import format_exc

from zope.component import adapts
from zope.interface import implements

from twisted.internet import defer
from twisted.python.failure import Failure
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.interfaces import IRRDDataSourceInfo
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.ZenUtils.Utils import prepId
from Products.Zuul.infos.template import RRDDataSourceInfo
from Products.ZenEvents import ZenEventClasses
from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin
from ..txcoroutine import coroutine

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
from ..utils import (
    check_for_network_error, pipejoin, cluster_state_value,
    save, errorMsgCheck, generateClearAuthEvents, get_dsconf,
    cluster_disk_state_string, cluster_csv_state_to_disk_map)
from . import send_to_debug

# Requires that txwinrm_utils is already imported.
from txwinrm.util import RequestError
from txwinrm.WinRMClient import SingleCommandClient
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
WINRS_SOURCETYPE = 'Windows Cluster'
BUFFER_SIZE = '$Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size (4096, 512);'
log = logging.getLogger('zen.MicrosoftWindows.ClusterDataSource')


def parse_stdout(result, check_stderr=False):
    """Get cmd result list with string elements separated by "|" inside,
    and return list of requested values or None, if there are no elements.
    """
    if check_stderr:
        stderr = ''.join(getattr(result, 'stderr', [])).strip()
        if stderr:
            raise Exception(stderr)
    try:
        stdout = ''.join(result.stdout).split('|')
    except AttributeError:
        return
    if filter(None, stdout):
        return stdout


class ClusterDataSource(PythonDataSource):
    """
    Subclass PythonDataSource to put a new datasources into Zenoss
    """

    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = 300

    sourcetypes = (WINRS_SOURCETYPE,)
    sourcetype = sourcetypes[0]
    plugin_classname = ZENPACKID + \
        '.datasources.ClusterDataSource.ClusterDataSourcePlugin'


class IClusterDataSourceInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the Shell datasource.
    """

    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))


class ClusterDataSourceInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the Shell plugin.
    """
    implements(IClusterDataSourceInfo)
    adapts(ClusterDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')


class ClusterDataSourcePlugin(PythonDataSourcePlugin):

    proxy_attributes = ConnectionInfoProperties

    def __init__(self, config=None):
        super(ClusterDataSourcePlugin, self).__init__(config=config)
        self.last_event_ts = {}

    @classmethod
    def config_key(cls, datasource, context):
        """
        Uniquely pull in datasources
        """
        return (context.device().id,
                datasource.getCycleTime(context),
                datasource.plugin_classname)

    @classmethod
    def params(cls, datasource, context):
        cluster = getattr(context, 'cluster', '')
        ownernode = getattr(context, 'ownernode', '')
        is_winservice_disabled = getattr(context, 'is_winservice_disabled', None)
        if is_winservice_disabled:
            disable_monitoring = is_winservice_disabled()
        else:
            disable_monitoring = False
        collector_timeout = getattr(context, 'zCollectorClientTimeout', 180)
        return dict(contexttitle=context.title,
                    ownernode=ownernode,
                    cluster=cluster,
                    collector_timeout=collector_timeout,
                    disable_monitoring=disable_monitoring)

    def build_command_line(self):
        pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

        psClusterCommands = []
        psClusterCommands.append(BUFFER_SIZE)
        psClusterCommands.append("import-module failoverclusters;")

        cluster_id_items = pipejoin('$_.Id $_.State')
        cluster_name_items = pipejoin('$_.Name $_.State')
        cluster_group_items = pipejoin('$_.Id $_.State $_.Name $_.OwnerNode')
        cluster_disk_items = pipejoin('$_.Id $_.State $_.Freespace')

        psClusterCommands.append(
            "get-clusterresource | where {{ $_.ResourceType.name -ne 'Physical Disk'}} | foreach {{'res-'+{}}};".format(cluster_name_items)
        )

        psClusterCommands.append(
            "get-clustergroup | foreach {{{}}};".format(cluster_group_items))

        psClusterCommands.append(
            "get-clusternode | foreach {{'node-'+{}}};".format(cluster_id_items))

        psClusterCommands.append("get-clusternetwork | foreach {{{}}};".format(cluster_id_items))

        psClusterCommands.append("get-clusternetworkinterface | foreach {{{}}};".format(cluster_id_items))

        psClusterCommands.append(
            "$csvNames = @();"
            "$clsSharedVolume = Get-ClusterSharedVolume -errorvariable "
            "volumeerr -erroraction 'silentlycontinue';"
            "if( -Not $volumeerr){{"
            "foreach ($volume in $clsSharedVolume) {{"
            "$volumeowner = $volume.OwnerNode.Name;"
            "$csvVolume = $volume.SharedVolumeInfo.Partition.Name;"
            "$csvNames = ($csvNames + $volume.Name);"
            "$csvtophysicaldisk = New-Object -TypeName PSObject -Property @{{"
            "Id = $csvVolume.substring(11, $csvVolume.length-13);"
            "FreeSpace = $volume.SharedVolumeInfo.Partition.Freespace;"
            "State = $volume.State;"
            "}}; $csvtophysicaldisk | foreach {{{}}} }};}};".format(
                cluster_disk_items)
        )

        psClusterCommands.append(
            "$use_cim = $PSVersionTable.PSVersion.Major -gt 2;"
            "if ($use_cim) {{"
            "$resources = Get-CimInstance -namespace"
            " 'root\MSCluster' -class 'MSCluster_Resource' "
            " | ? {{$_.Type -eq 'Physical Disk'}};"
            "}} else {{$resources = Get-WmiObject -class MSCluster_Resource "
            "-namespace root\MSCluster -filter \\\"Type='Physical Disk'\\\";}}"
            "foreach ($resource in $resources) {{"
            "if ($csvNames.Contains($resource.Name)) {{ continue; }}"
            "$rsc = get-clusterresource -name $resource.Name;"
            "if ($use_cim) {{"
            "$disks = Get-CimAssociatedInstance $resource -ResultClassName "
            "'MSCluster_Disk'; }} else {{ "
            "$disks = $resource.GetRelated('MSCluster_Disk');}}"
            "foreach ($dsk in $disks) {{"
            "if ($use_cim) {{"
            "$partitions = Get-CimAssociatedInstance $dsk -ResultClassName "
            '"MSCluster_DiskPartition";}} else {{'
            "$partitions = $dsk.GetRelated('MSCluster_DiskPartition');}}"
            "if ($partitions -ne $null) {{"
            "foreach ($prt in $partitions) {{"
            "$physicaldisk = New-Object -TypeName PSObject -Property @{{"
            "Id = $rsc.Id;FreeSpace = $prt.FreeSpace * 1mb;"
            "State = $resource.State;}}; "
            "$physicaldisk | foreach {{{cluster_disk_items}}};}}}}else {{"
            "$physicaldisk = New-Object -TypeName PSObject -Property @{{"
            "Id = $rsc.Id;State = $resource.State;FreeSpace = -1}};"
            "$physicaldisk | foreach {{{cluster_disk_items}}} }};}}}}"
            "".format(cluster_disk_items=cluster_disk_items)
        )

        script = "\"& {{{}}}\"".format(''.join(psClusterCommands))
        return pscommand, script

    @coroutine
    def collect(self, config):
        conn_info = createConnectionInfo(config.datasources[0])
        command = SingleCommandClient(conn_info)
        pscommand, script = self.build_command_line()
        results = yield command.run_command(pscommand, script)
        defer.returnValue(results)

    @save
    def onSuccess(self, results, config):
        log.debug('Cluster collection results: {}'.format(results))
        data = self.new_data()
        for result in results.stdout:
            # ignore any empty lines
            if len(result) <= 0:
                continue
            cluster_line = result.split('|')
            ownernode = None
            if len(cluster_line) == 2:
                comp, state = cluster_line
                name = ''
            elif len(cluster_line) == 3:
                comp, state, freespace = cluster_line
            elif len(cluster_line) == 4:
                comp, state, name, ownernode = cluster_line
            else:
                log.debug('Unable to parse cluster result {} on {}'.format(
                    result, config.id))
                continue
            comp = prepId(comp)
            dsconf = get_dsconf(
                config.datasources, str(comp), param='contexttitle')
            if dsconf is None:
                # component probably not modeled, see ZEN-23142
                continue
            if dsconf.params.get('disable_monitoring', False):
                # component's corresponding Windows Service is disabled
                # and zWinClusterResourcesMonitoringDisabled is True
                continue
            try:
                # specific for cluster disk component
                data['values'][comp]['state'] = int(state)
                state = cluster_disk_state_string(int(state))
            except ValueError:
                # cluster shared volume returns text. e.g. 'Online'
                data['values'][comp]['state'] = cluster_csv_state_to_disk_map(
                    state)
            try:
                if freespace != '-1':
                    # don't write dp if -1.  probably means unallocated disk
                    # and freespace would have no meaning
                    data['values'][comp]['freespace'] = int(freespace)
            except Exception:
                # handles all other cases
                data['values'][comp]['state'] = cluster_state_value(state), 'N'
            severity = {
                'Online': ZenEventClasses.Clear,
                'Up': ZenEventClasses.Clear,
                'Down': ZenEventClasses.Critical,
                'Offline': ZenEventClasses.Critical,
                'PartialOnline': ZenEventClasses.Error,
                'Failed': ZenEventClasses.Critical,
                'Paused': ZenEventClasses.Warning,
            }.get(state, ZenEventClasses.Info)

            data['events'].append(dict(
                eventClass=dsconf.eventClass or "/Status",
                eventClassKey='clusterComponentStatus',
                eventKey=dsconf.eventKey,
                severity=severity,
                summary='Last state of component {} was {}'.format(
                    dsconf.params['contexttitle'], state),
                device=config.id,
                component=prepId(dsconf.component)
            ))
            # if the ownernode has changed for any cluster service,
            # we need to remodel
            if ownernode and dsconf.params['ownernode'] != ownernode.strip():
                component_key = (config.id, dsconf.component)
                last_event_ts = self.last_event_ts.get(component_key, 0)
                default_wait_time = (dsconf.params['collector_timeout'] * 1.5)
                if time.time() - last_event_ts >= default_wait_time:
                    last_event_ts = time.time()
                    data['events'].append(dict(
                        eventClassKey='clusterOwnerChange',
                        eventKey='clusterCollection',
                        severity=ZenEventClasses.Info,
                        summary='OwnerNode of cluster {} for cluster service {} changed to {}'.format(
                                dsconf.params['cluster'],
                                name.strip(),
                                ownernode),
                        device=config.id,
                        component=prepId(dsconf.component)
                    ))
                    self.last_event_ts[component_key] = last_event_ts

        # look for any components not returned
        for dsconf in config.datasources:
            if dsconf.component not in data['values'] and not dsconf.params.get('disable_monitoring'):
                # no state returned for component
                log.debug('No state value for cluster component {}'.format(dsconf.component))
                data['events'].append(dict(
                    severity=dsconf.severity,
                    eventClass=dsconf.eventClass,
                    component=dsconf.component,
                    summary='No state value returned for {}'.format(dsconf.component)))

        data['events'].append(dict(
            severity=ZenEventClasses.Clear,
            eventClass='/Status',
            eventKey='clusterCollection',
            summary='cluster: successful collection',
            device=config.id))
        data['events'].append(dict(
            severity=ZenEventClasses.Clear,
            eventClass='/Status',
            eventKey='datasourceWarning_{0}'.format(config.datasources[0].datasource),
            summary='cluster: successful collection',
            device=config.id))
        generateClearAuthEvents(config, data['events'])
        return data

    @save
    def onError(self, result, config):
        log.debug('ClusterDataSource error on {}: {}'.format(
            config.id, result))
        logg = log.error
        msg, event_class = check_for_network_error(result, config)
        eventKey = 'clusterCollection'
        if isinstance(result, Failure):
            if isinstance(result.value, RequestError):
                args = result.value.args
                msg = args[0] if args else format_exc(result.value)
            elif send_to_debug(result):
                logg = log.debug
            else:
                eventKey = 'datasourceWarning_{0}'.format(
                    config.datasources[0].datasource
                )
                value = str(result.value)
                if not value:
                    value = 'Received {}'.format(result.value.__class__.__name__)
                msg = '{0} on {1}'.format(str(result.value), config)
                logg = log.warn

        logg(msg)
        data = self.new_data()
        if not errorMsgCheck(config, data['events'], result.value.message):
            data['events'].append(dict(
                eventClass='/Status',
                severity=ZenEventClasses.Warning,
                eventKey=eventKey,
                summary='Cluster: ' + msg,
                device=config.id))
        return data
