##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Windows Operating System Collection

"""
import logging
import re

from Products.DataCollector.plugins.DataMaps \
    import MultiArgs, ObjectMap, RelationshipMap
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from Products.ZenUtils.IpUtil import checkip, IpAddressError

from Products.ZenUtils.Utils import prepId
from ZenPacks.zenoss.Microsoft.Windows.utils import (
        addLocalLibPath,
        lookup_architecture,
        lookup_routetype,
        lookup_protocol,
        lookup_drivetype,
        lookup_zendrivetype,
        guessBlockSize,
        )

addLocalLibPath()

from txwinrm.collect import WinrmCollectClient


class WinOS(PythonPlugin):

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        )

    WinRMQueries = [
        'select * from Win32_ComputerSystem',
        'select * from Win32_SystemEnclosure',
        'select * from Win32_OperatingSystem',
        'select * from Win32_Processor',
        'select * from Win32_CacheMemory',
        'select * from Win32_IP4RouteTable',
        'select * from Win32_NetworkAdapterConfiguration',
        'select * from Win32_logicaldisk',
        'select * from Win32_Volume',
        'select * from Win32_MappedLogicalDisk'
        ]

    def collect(self, device, log):

        username = device.zWinUser
        password = device.zWinPassword
        hostname = device.manageIp

        winrm = WinrmCollectClient(logging.getLogger())

        results = winrm.do_collect(
                    hostname,
                    username,
                    password,
                    self.WinRMQueries)

        return results

    def process(self, device, results, log):

        log.info('Modeler %s processing data for device %s',
            self.name(), device.id)

        sysEnclosure = results['select * from Win32_SystemEnclosure'][0]
        computerSystem = results['select * from Win32_ComputerSystem'][0]
        operatingSystem = results['select * from Win32_OperatingSystem'][0]
        sysProcessor = results['select * from Win32_Processor']
        netRoute = results['select * from Win32_IP4RouteTable']
        netInt = results['select * from Win32_NetworkAdapterConfiguration']
        fsDisk = results['select * from Win32_logicaldisk']
        #fsVol = results['select * from Win32_Volume']
        #fsMap = results['select * from Win32_MappedLogicalDisk']

        #import pdb; pdb.set_trace()
        maps = []

        # Hardware Map
        hw_om = ObjectMap(compname='hw')
        hw_om.serialNumber = sysEnclosure.SerialNumber
        hw_om.tag = sysEnclosure.Tag
        hw_om.totalMemory = int(operatingSystem.TotalVisibleMemorySize) * 1024
        maps.append(hw_om)

        # OS Map
        os_om = ObjectMap(compname='os')
        os_om.totalSwap = int(operatingSystem.TotalVirtualMemorySize) * 1024
        maps.append(os_om)

        # Processor Map
        mapProc = []
        for proc in sysProcessor:
            proc_om = ObjectMap()
            proc_om.id = prepId(proc.DeviceID)
            proc_om.caption = proc.Caption
            proc_om.title = proc.Name
            proc_om.numbercore = proc.NumberOfCores
            proc_om.status = proc.Status
            proc_om.architecture = lookup_architecture(int(proc.Architecture))
            proc_om.clockspeed = proc.MaxClockSpeed  # MHz
            mapProc.append(proc_om)

        maps.append(RelationshipMap(
            relname="winrmproc",
            compname="hw",
            modname="ZenPacks.zenoss.Microsoft.Windows.WinProc",
            objmaps=mapProc))

        # OS Map

        # Operating System Map
        operatingSystem.Caption = re.sub(r'\s*\S*Microsoft\S*\s*', '',
                                    operatingSystem.Caption)

        cs_om = ObjectMap()
        cs_om.title = computerSystem.DNSHostName
        cs_om.setHWProductKey = MultiArgs(computerSystem.Model,
                                        computerSystem.Manufacturer)

        cs_om.setOSProductKey = MultiArgs(operatingSystem.Caption,
                                        operatingSystem.Manufacturer)

        cs_om.snmpSysName = computerSystem.Name
        cs_om.snmpContact = computerSystem.PrimaryOwnerName
        cs_om.snmpDescr = computerSystem.Caption

        maps.append(cs_om)

        # Interface Map
        mapInter = []

        skipifregex = getattr(device, 'zInterfaceMapIgnoreNames', None)

        for inter in netInt:
            ips = []

            if inter.Description is not None:
                if skipifregex and re.match(skipifregex, inter.Description):
                    log.debug("Interface {intname} matched regex -- skipping".format(
                        intname=inter.Description))
                    continue

            if getattr(inter, 'IPAddress', None) != None:
                for ipRecord, ipMask in zip([inter.IPAddress], [inter.IPSubnet]):
                    try:
                        checkip(ipRecord)
                        if not ipMask:
                            raise IpAddressError()

                        ipEntry = "{ipaddress}/{ipsubnet}".format(ipaddress=ipRecord,
                                ipsubnet=ipMask)
                        ips.append(ipEntry)
                    except IpAddressError:
                        log.debug("Invalid IP Address {ipaddress} encountered "
                                "skipped".format(ipaddress=ipRecord))

            #import pdb; pdb.set_trace()
            int_om = ObjectMap()
            int_om.id = prepId(inter.Description)
            int_om.setIpAddresses = ips
            int_om.interfaceName = int_om.description = inter.Description
            int_om.macaddress = inter.MACAddress
            int_om.mtu = inter.MTU
            int_om.monitor = int_om.operStatus = bool(inter.IPEnabled)
            try:
                int_om.ifindex = int(inter.InterfaceIndex)
            except AttributeError:
                int_om.ifindex = int(inter.Index)

            mapInter.append(int_om)

        maps.append(RelationshipMap(
            relname="interfaces",
            compname="os",
            modname="Products.ZenModel.IpInterface",
            objmaps=mapInter))

        # Network Route Map
        mapRoute = []
        for route in netRoute:
            route_om = ObjectMap()
            route_om.id = prepId(route.Destination)
            route_om.routemask = self.maskToBits(route.Mask)
            route_om.setInterfaceIndex = int(route.InterfaceIndex)
            route_om.setNextHopIp = route.NextHop
            route_om.routeproto = lookup_protocol(int(route.Protocol))
            route_om.routetype = lookup_routetype(int(route.Type))
            route_om.metric1 = route.Metric1
            route_om.metric2 = route.Metric2
            route_om.metric3 = route.Metric3
            route_om.metric4 = route.Metric4
            route_om.metric5 = route.Metric5
            route_om.routemask = self.maskToBits(route.Mask)
            route_om.setTarget = route_om.id + "/" + str(route_om.routemask)
            route_om.id += "_" + str(route_om.routemask)

            if route_om.routemask == 32:
                continue

            mapRoute.append(route_om)

        maps.append(RelationshipMap(
            relname="routes",
            compname="os",
            modname="Products.ZenModel.IpRouteEntry",
            objmaps=mapRoute))

        # File System Map
        skipfsnames = getattr(device, 'zFileSystemMapIgnoreNames', None)
        skipfstypes = getattr(device, 'zFileSystemMapIgnoreTypes', None)

        mapDisk = []
        for disk in fsDisk:
            disk_om = ObjectMap()
            disk_om.mount = "{driveletter} (Serial Number: {serialnumber}) - {name}".format(
                driveletter=disk.Name,
                serialnumber=disk.VolumeSerialNumber,
                name=disk.VolumeName)

            #Check if drive description matches skip names
            if skipfsnames and re.search(skipfsnames, disk_om.mount):
                continue

            disk_om.drivetype = int(disk.DriveType)

            #Check for excluded drives
            if skipfstypes:
                #Get mapping of Windows Drive types to Zenoss types for exclusion
                zentype = lookup_zendrivetype(disk_om.drivetype)
                for mapdisktype in zentype:
                    if mapdisktype in skipfstypes:
                        log.info("{drivename} drive's filesystem {filesystem}"
                                " has been excluded").format(
                            drivename=disk.Name,
                            filesystem=lookup_drivetype(disk_om.drivetype))
                        break

            disk_om.monitor = (disk.Size and int(disk.MediaType) in (12, 0))
            disk_om.storageDevice = disk.Name
            disk_om.drivetype = lookup_drivetype(disk_om.drivetype)
            disk_om.type = disk.FileSystem
            if disk.Size:
                if not disk.BlockSize:
                    disk.BlockSize = guessBlockSize(disk.Size)
                disk_om.blockSize = int(disk.BlockSize)
                disk_om.totalBlocks = int(disk.Size) / disk_om.blockSize
            disk_om.maxNameLen = disk.MaximumComponentLength
            disk_om.id = self.prepId(disk.DeviceID)
            mapDisk.append(disk_om)

        maps.append(RelationshipMap(
            relname="filesystems",
            compname="os",
            modname="Products.ZenModel.FileSystem",
            objmaps=mapDisk))

        return maps
