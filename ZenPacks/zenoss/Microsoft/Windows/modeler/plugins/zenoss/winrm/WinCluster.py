##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Windows Cluster System Collection

"""
import logging
from socket import gaierror
from twisted.internet import defer

from Products.DataCollector.plugins.DataMaps import ObjectMap, RelationshipMap

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath
from Products.ZenUtils.IpUtil import asyncIpLookup
from ZenPacks.zenoss.Microsoft.Windows.utils import pipejoin, save

from txwinrm.WinRMClient import SingleCommandClient

addLocalLibPath()
log = logging.getLogger("zen.MicrosoftCluster")


class ClusterCommander(object):
    def __init__(self, conn_info):
        self.winrs = SingleCommandClient(conn_info)

    pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
        "-OutputFormat TEXT -Command "

    psClusterCommands = []
    psClusterCommands.append("$Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size (512, 512);")
    psClusterCommands.append("import-module failoverclusters;")

    def run_command(self, command):
        """Run command for powershell failover clusters"""
        if isinstance(command, str):
            command = command.splitlines()
        command = "\"& {{{}}}\"".format(
            ''.join(self.psClusterCommands + command)
        )
        return self.winrs.run_command(self.pscommand, ps_script=command)


class WinCluster(WinRMPlugin):

    deviceProperties = WinRMPlugin.deviceProperties + (
        'zFileSystemMapIgnoreNames',
        'zFileSystemMapIgnoreTypes',
        'zInterfaceMapIgnoreNames',
    )

    @defer.inlineCallbacks
    def collect(self, device, log):
        maps = {}

        conn_info = self.conn_info(device)
        conn_info = conn_info._replace(timeout=device.zCollectorClientTimeout - 5)
        cmd = ClusterCommander(conn_info)

        domain = yield cmd.run_command("(gwmi WIN32_ComputerSystem).Domain;")
        domain = domain.stdout[0] if domain.stdout else ''

        resourceCommand = []
        resourceCommand.append(
            'get-clustergroup | foreach {%s};' % pipejoin(
                '$_.Name $_.IsCoreGroup $_.OwnerNode '
                '$_.State $_.Description $_.Id $_.Priority'
            )
        )
        resourceCommand.append('write-host "====";')
        resourceCommand.append(
            "get-clusterresource | where { $_.ResourceType.name -ne 'Physical Disk'} | foreach {%s};" % pipejoin(
                '$_.Name $_.OwnerGroup $_.OwnerNode $_.State $_.Description $_.Cluster'
            )
        )
        resource = yield cmd.run_command("".join(resourceCommand))

        clusternode = yield cmd.run_command(
            "get-clusternode | foreach {%s};" % pipejoin(
                '$_.Name $_.NodeWeight $_.DynamicWeight $_.Id $_.State')
        )

        disk_properties = pipejoin(
            '$_.Id $_.Name $_.VolumePath $_.OwnerNode $_.DiskNumber $_.PartitionNumber $_.Size $_.FreeSpace $_.State $_.OwnerGroup')

        clusterDiskCommand = []
        clusterDiskCommand.append(
            "$volumeInfo = Get-Disk | Get-Partition | Select DiskNumber, @{{"
            "Name='Volume';Expression={{Get-Volume -Partition $_ | Select -ExpandProperty ObjectId;}}}};"
            "$clusterSharedVolume = Get-ClusterSharedVolume;"
            "foreach ($volume in $clusterSharedVolume) {{"
            "$volumeowner = $volume.OwnerNode.Name;"
            "$csvVolume = $volume.SharedVolumeInfo.Partition.Name;"
            "$csvdisknumber = ($volumeinfo | where {{ $_.Volume -eq $csvVolume}}).Disknumber;"
            "$csvtophysicaldisk = New-Object -TypeName PSObject -Property @{{"
            "Id = $csvVolume.substring(11, $csvVolume.length-13);"
            "Name = $volume.Name;"
            "VolumePath = $volume.SharedVolumeInfo.FriendlyVolumeName;"
            "OwnerNode = $volumeowner;"
            "DiskNumber = $csvdisknumber;"
            "PartitionNumber = $volume.SharedVolumeInfo.PartitionNumber;"
            "Size = $volume.SharedVolumeInfo.Partition.Size;"
            "FreeSpace = $volume.SharedVolumeInfo.Partition.Freespace;"
            "State = $volume.State;"
            "OwnerGroup = 'Cluster Shared Volume';}};"
            "$csvtophysicaldisk | foreach {{{}}};}};".format(disk_properties)
        )

        clusterDiskCommand.append(
            "$resources = Get-CimInstance -namespace"
            " 'root\MSCluster' -class 'MSCluster_Resource' "
            " | ? {{$_.Type -eq 'Physical Disk'}};"
            "foreach ($resource in $resources) {{"
            "$rsc = get-clusterresource -name $resource.Name;"
            "$disks = Get-CimAssociatedInstance $resource -ResultClassName "
            '"MSCluster_Disk";'
            "foreach ($dsk in $disks) {{"
            "$partitions = Get-CimAssociatedInstance $dsk -ResultClassName "
            '"MSCluster_DiskPartition";'
            "if ($partitions -ne $null) {{"
            "foreach ($prt in $partitions) {{"
            "$physicaldisk = New-Object -TypeName PSObject -Property @{{"
            "Id = $rsc.Id;OwnerNode = $rsc.OwnerNode;OwnerGroup = $rsc.OwnerGroup;"
            "Name = $rsc.Name;VolumePath = $prt.Path;DiskNumber = $dsk.Number;"
            "PartitionNumber = $prt.PartitionNumber;Size = $prt.TotalSize * 1mb;"
            "FreeSpace = $prt.FreeSpace * 1mb;State = $rsc.State;}}; "
            "$physicaldisk | foreach {{{}}};}}}}else {{"
            "$physicaldisk = New-Object -TypeName PSObject -Property @{{"
            "Id = $rsc.Id;OwnerNode = $rsc.OwnerNode;"
            "OwnerGroup = $rsc.OwnerGroup;Name = $rsc.Name;DiskNumber = $dsk.Number;"
            "State = $rsc.State;Size = $dsk.Size;VolumePath = 'No Volume';"
            "PartitionNumber = 'No Partitions';FreeSpace = 'N/A'}};"
            "$physicaldisk | foreach {{{}}};}}}}}};".format(disk_properties, disk_properties)
        )

        clusterdisk = yield cmd.run_command("".join(clusterDiskCommand))

        clusterNetworkCommand = []
        clusterNetworkCommand.append(
            'get-clusternetwork | foreach {%s};' % pipejoin(
                '$_.Id $_.Name $_.Description $_.State $_.Role')
        )
        clusterNetworkCommand.append('write-host "====";')
        clusterNetworkCommand.append(
            'get-clusternetworkInterface | foreach{%s}' % pipejoin(
                '$_.Id $_.Name $_.Node $_.Network '
                '$_.ipv4addresses $_.Adapter $_.State')
        )
        clusternetworks = yield cmd.run_command("".join(clusterNetworkCommand))

        maps['resources'] = resource.stdout

        nodes = {}
        if domain:
            for node in clusternode.stdout:
                node_name = node.split('|')[0] + '.' + domain
                try:
                    nodes[node_name] = yield asyncIpLookup(node_name)
                except(gaierror):
                    log.warning('Unable to resolve hostname {0}'.format(node_name))
                    continue

        maps['nodes'] = nodes
        maps['nodes_data'] = clusternode.stdout
        maps['clusterdisk'] = clusterdisk.stdout
        maps['clusternetworks'] = clusternetworks.stdout
        maps['domain'] = domain

        defer.returnValue(maps)

    @save
    def process(self, device, results, log):
        log.info('Modeler %s processing data for device %s',
                 self.name(), device.id)
        maps = []

        map_resources_oms = []
        map_nodes_oms = []
        map_networks_oms = []
        ownergroups = {}
        map_apps_to_resource = {}
        node_ownergroups = {}
        map_disks_to_node = {}
        map_interfaces_to_node = {}

        nodes = results['nodes']
        cs_om = ObjectMap()
        cs_om.setClusterHostMachines = nodes
        maps.append(cs_om)

        # Cluster Resource Maps
        resources = []
        applications = []

        resources_res = results['resources']
        if resources_res:
            res_spliter_index = resources_res.index("====")
            resources = resources_res[:res_spliter_index]
            applications = resources_res[res_spliter_index + 1:]

        # This section is for ClusterService class
        for resource in resources:
            resourceline = resource.split("|")
            res_om = ObjectMap()

            res_om.id = self.prepId(resourceline[5])
            res_om.title = resourceline[0]
            res_om.coregroup = resourceline[1]
            res_om.ownernode = resourceline[2]
            res_om.description = resourceline[4]
            res_om.priority = resourceline[6]
            res_om.domain = results['domain']

            if res_om.title not in ownergroups:
                ownergroups[res_om.title] = res_om.id

            map_resources_oms.append(res_om)
        # Cluster Application and Services

        # This section is for ClusterResrouce class
        for app in applications:
            appline = app.split("|")
            app_ownergroup = appline[1]

            if app_ownergroup in ownergroups:
                app_om = ObjectMap()
                app_om.id = self.prepId('res-{0}'.format(appline[0]))
                app_om.title = appline[0]
                app_om.ownernode = appline[2]
                app_om.description = appline[4]
                app_om.ownergroup = app_ownergroup
                app_om.cluster = appline[5]
                app_om.domain = results['domain']

                groupid = ownergroups[app_om.ownergroup]

                appsom = []
                if groupid in map_apps_to_resource:
                    appsom = map_apps_to_resource[groupid]
                appsom.append(app_om)
                map_apps_to_resource[groupid] = appsom

        # Fixes ZEN-23142
        # Remove ClusterServices without any associated ClusterResources configured
        for m in map_resources_oms:
            if m.id not in map_apps_to_resource.keys():
                map_resources_oms.remove(m)

        maps.append(RelationshipMap(
            compname="os",
            relname="clusterservices",
            modname="ZenPacks.zenoss.Microsoft.Windows.ClusterService",
            objmaps=map_resources_oms
        ))

        for resourceid, apps in map_apps_to_resource.items():
            maps.append(RelationshipMap(
                compname="os/clusterservices/" + resourceid,
                relname="clusterresources",
                modname="ZenPacks.zenoss.Microsoft.Windows.ClusterResource",
                objmaps=apps
            ))

        # This section is for ClusterNode class
        nodes_data = results['nodes_data']

        for node in nodes_data:
            nodeline = node.split("|")
            node_om = ObjectMap()
            node_om.id = self.prepId('node-{0}'.format(nodeline[3]))
            node_om.title = nodeline[0]
            node_om.ownernode = nodeline[0]
            node_om.assignedvote = nodeline[1]
            node_om.currentvote = nodeline[2]
            node_om.domain = results['domain']

            if node_om.title not in node_ownergroups:
                node_ownergroups[node_om.title] = node_om.id

            map_nodes_oms.append(node_om)
            map_disks_to_node[node_om.id] = []

        # This section is for ClusterDisk class
        clusterdisk = results['clusterdisk']

        for disk in clusterdisk:
            diskline = disk.split("|")
            disk_ownernode = diskline[3]

            if disk_ownernode in node_ownergroups:
                disk_om = ObjectMap()
                disk_om.id = self.prepId(diskline[0])
                disk_om.title = diskline[1]
                disk_om.volumepath = diskline[2]
                disk_om.ownernode = disk_ownernode
                disk_om.disknumber = diskline[4]
                disk_om.partitionnumber = diskline[5]
                try:
                    disk_om.size = int(diskline[6])
                except Exception:
                    log.debug('disk size not formatted correctly')
                    disk_om.size = -1
                disk_om.assignedto = diskline[9]
                disk_om.domain = results['domain']

                nodeid = node_ownergroups[disk_om.ownernode]
                disksom = []
                if nodeid in map_disks_to_node:
                    disksom = map_disks_to_node[nodeid]
                disksom.append(disk_om)
                map_disks_to_node[nodeid] = disksom

        # This section is for ClusterInterface class
        clusternetworks = []
        nodeinterfaces = []

        cluster_network_res = results['clusternetworks']
        if cluster_network_res:
            net_spliter_index = cluster_network_res.index("====")
            clusternetworks = cluster_network_res[:net_spliter_index]
            nodeinterfaces = cluster_network_res[net_spliter_index + 1:]

        for interface in nodeinterfaces:
            intfline = interface.split("|")
            intf_node = intfline[2]

            if intf_node in node_ownergroups:
                interface_om = ObjectMap()
                interface_om.id = self.prepId(intfline[0])
                interface_om.title = intfline[1]
                interface_om.node = intf_node
                interface_om.network = intfline[3]
                interface_om.ipaddresses = intfline[4]
                interface_om.adapter = intfline[5]
                interface_om.domain = results['domain']

                intfnodeid = node_ownergroups[interface_om.node]
                intfom = []
                if intfnodeid in map_interfaces_to_node:
                    intfom = map_interfaces_to_node[intfnodeid]
                intfom.append(interface_om)
                map_interfaces_to_node[intfnodeid] = intfom

        maps.append(RelationshipMap(
            compname="os",
            relname="clusternodes",
            modname="ZenPacks.zenoss.Microsoft.Windows.ClusterNode",
            objmaps=map_nodes_oms
        ))

        for nodeid, disks in map_disks_to_node.items():
            maps.append(RelationshipMap(
                compname="os/clusternodes/" + nodeid,
                relname="clusterdisks",
                modname="ZenPacks.zenoss.Microsoft.Windows.ClusterDisk",
                objmaps=disks
            ))

        for nodeid, interface in map_interfaces_to_node.items():
            maps.append(RelationshipMap(
                compname="os/clusternodes/" + nodeid,
                relname="clusterinterfaces",
                modname="ZenPacks.zenoss.Microsoft.Windows.ClusterInterface",
                objmaps=interface
            ))

        # This section is for ClusterNetwork class
        for network in clusternetworks:
            netline = network.split("|")
            netrole = {
                '0': 'Not allowed',
                '1': 'Cluster only',
                '3': 'Cluster and Client'
            }.get(netline[4], '0')

            net_om = ObjectMap()
            net_om.id = self.prepId(netline[0])
            net_om.title = netline[1]
            net_om.description = netline[2]
            net_om.role = netrole
            net_om.domain = results['domain']

            map_networks_oms.append(net_om)

        maps.append(RelationshipMap(
            compname="os",
            relname="clusternetworks",
            modname="ZenPacks.zenoss.Microsoft.Windows.ClusterNetwork",
            objmaps=map_networks_oms
        ))
        return maps
