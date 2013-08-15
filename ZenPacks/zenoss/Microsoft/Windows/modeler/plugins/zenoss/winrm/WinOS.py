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
import re
import string
from pprint import pformat
from Products.DataCollector.plugins.DataMaps import MultiArgs, ObjectMap, RelationshipMap
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from Products.DataCollector.plugins.zenoss.snmp.CpuMap import getManufacturerAndModel
from Products.ZenUtils.IpUtil import checkip, parse_iprange, IpAddressError
from Products.ZenUtils.Utils import prepId
from Products.Zuul.utils import safe_hasattr
from ZenPacks.zenoss.Microsoft.Windows.utils import lookup_architecture, lookup_routetype, lookup_protocol, \
    lookup_drivetype, lookup_zendrivetype, guessBlockSize, addLocalLibPath, lookup_operstatus

addLocalLibPath()

from txwinrm.collect import ConnectionInfo, WinrmCollectClient, \
    create_enum_info

ENUM_INFOS = dict(
    sysEnclosure=create_enum_info('select * from Win32_SystemEnclosure'),
    computerSystem=create_enum_info('select * from Win32_ComputerSystem'),
    operatingSystem=create_enum_info('select * from Win32_OperatingSystem'),
    sysProcessor=create_enum_info('select * from Win32_Processor'),
    cacheMemory=create_enum_info('select * from Win32_CacheMemory'),
    netRoute=create_enum_info('select * from Win32_IP4RouteTable'),
    netInt=create_enum_info('select * from Win32_NetworkAdapter'),
    netConf=create_enum_info('select * from Win32_NetworkAdapterConfiguration'),
    fsDisk=create_enum_info('select * from Win32_logicaldisk'),
    fsVol=create_enum_info('select * from Win32_Volume'),
    fsMap=create_enum_info('select * from Win32_MappedLogicalDisk'))

SINGLETON_KEYS = ["sysEnclosure", "computerSystem", "operatingSystem"]

_transTable = string.maketrans("#()/", "_[]_")


def standardizeInstance(rawInstance):
    """
    Convert a raw perfmon instance name into a standardized one by replacing
    unfriendly characters with one that Windows expects.
    """
    return rawInstance.translate(_transTable)


class WinOSResult(object):
    pass


class WinOS(PythonPlugin):

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        'zFileSystemMapIgnoreNames',
        'zFileSystemMapIgnoreTypes',
        'zInterfaceMapIgnoreNames',
        'zWinRMPort',
        )

    def collect(self, device, log):
        hostname = device.manageIp
        username = device.zWinUser
        auth_type = 'kerberos' if '@' in username else 'basic'
        password = device.zWinPassword
        scheme = 'http'
        port = int(device.zWinRMPort)
        connectiontype = 'Keep-Alive'

        winrm = WinrmCollectClient()
        conn_info = ConnectionInfo(
            hostname,
            auth_type,
            username,
            password,
            scheme,
            port,
            connectiontype)

        results = winrm.do_collect(conn_info, ENUM_INFOS.values())
        return results

    def process(self, device, results, log):
        log.info('Modeler %s processing data for device %s',
                 self.name(), device.id)

        res = WinOSResult()
        for key, enum_info in ENUM_INFOS.iteritems():
            value = results[enum_info]
            if key in SINGLETON_KEYS:
                value = value[0]
            setattr(res, key, value)

        maps = []

        # Hardware Map
        hw_om = ObjectMap(compname='hw')
        hw_om.serialNumber = res.sysEnclosure.SerialNumber
        hw_om.tag = res.sysEnclosure.Tag

        if safe_hasattr(res.operatingSystem, "TotalVisibleMemorySize"):
            hw_om.totalMemory = 1024 * int(res.operatingSystem.TotalVisibleMemorySize)
        else:
            log.warn("Win32_OperatingSystem query did not respond with TotalVisibleMemorySize.\n{0}"
                     .format(pformat(sorted(vars(res.operatingSystem).keys()))))
        maps.append(hw_om)

        # OS Map
        os_om = ObjectMap(compname='os')
        os_om.totalSwap = \
            int(res.operatingSystem.TotalVirtualMemorySize) * 1024
        maps.append(os_om)

        # Processor Map
        mapProc = []
        for proc in res.sysProcessor:
            proc_om = ObjectMap()
            proc_om.id = prepId(proc.DeviceID)
            proc_om.caption = proc.Caption
            proc_om.title = proc.Name
            if safe_hasattr(proc, 'NumberOfCores'):
                proc_om.numbercore = proc.NumberOfCores
            proc_om.status = proc.Status
            proc_om.architecture = lookup_architecture(int(proc.Architecture))
            proc_om.clockspeed = proc.MaxClockSpeed  # MHz
            proc_om.setProductKey = getManufacturerAndModel(' '.join([proc.Manufacturer, proc.Description]))
            mapProc.append(proc_om)

        maps.append(RelationshipMap(
            relname="winrmproc",
            compname="hw",
            modname="ZenPacks.zenoss.Microsoft.Windows.WinProc",
            objmaps=mapProc))

        # OS Map

        # Operating System Map
        res.operatingSystem.Caption = re.sub(r'\s*\S*Microsoft\S*\s*', '',
                                             res.operatingSystem.Caption)

        cs_om = ObjectMap()
        cs_om.title = res.computerSystem.DNSHostName
        cs_om.setHWProductKey = MultiArgs(res.computerSystem.Model,
                                          res.computerSystem.Manufacturer)
        osCaption = '{0} - {1}'.format(res.operatingSystem.Caption,
                                        res.operatingSystem.CSDVersion)

        cs_om.setOSProductKey = MultiArgs(osCaption,
                                          res.operatingSystem.Manufacturer)

        cs_om.snmpSysName = res.computerSystem.Name
        cs_om.snmpContact = res.computerSystem.PrimaryOwnerName
        cs_om.snmpDescr = res.computerSystem.Caption

        maps.append(cs_om)

        # Interface Map
        mapInter = []

        skipifregex = getattr(device, 'zInterfaceMapIgnoreNames', None)
        perfmonInstanceMap = self.buildPerfmonInstances(res.netConf, log)
        for inter in res.netInt:
            #Get the Network Configuration data for this interface

            for intconf in res.netConf:
                if intconf.Index == inter.Index:
                    interconf = intconf
                    continue

            ips = []

            if inter.Description is not None:
                if skipifregex and re.match(skipifregex, inter.Description):
                    log.debug("Interface {intname} matched regex -- skipping"
                              .format(intname=inter.Description))
                    continue

            if interconf.MACAddress is None:
                continue

            if getattr(interconf, 'IPAddress', None) is not None:
                arrIPaddress = parse_iprange(interconf.IPAddress)

                for ipRecord in arrIPaddress:
                    try:
                        checkip(ipRecord)

                        ipEntry = "{ipaddress}/{ipsubnet}".format(
                                  ipaddress=ipRecord, ipsubnet=interconf.IPSubnet)
                        ips.append(ipEntry)
                    except IpAddressError:
                        log.debug("Invalid IP Address {0} encountered and "
                                "skipped".format(ipRecord))

            int_om = ObjectMap()
            int_om.id = prepId(standardizeInstance(interconf.Description))
            int_om.setIpAddresses = ips
            int_om.interfaceName = inter.Description
            if getattr(inter, 'NetConnectionID') is not None:
                int_om.description = inter.NetConnectionID
            else:
                int_om.description = interconf.Description
            int_om.macaddress = inter.MACAddress

            if getattr(interconf, 'MTU', 0) is not None:
                int_om.mtu = interconf.MTU
            else:
                int_om.mtu = 0

            if getattr(inter, 'Speed', 0) is not None:
                int_om.speed = inter.Speed
            else:
                int_om.speed = 0

            int_om.duplex = 0
            int_om.type = inter.AdapterType

            try:
                int_om.adminStatus = int(lookup_operstatus(inter.NetEnabled))
            except (AttributeError):
                int_om.adminStatus = 0

            int_om.operStatus = int(lookup_operstatus(interconf.IPEnabled))

            try:
                int_om.ifindex = int(inter.InterfaceIndex)
            except (AttributeError, TypeError):
                int_om.ifindex = int(inter.Index)

            if inter.Index in perfmonInstanceMap:
                int_om.perfmonInstance = perfmonInstanceMap[inter.Index]
            else:
                log.warning("Adapter '%s':%d does not have a perfmon "
                            "instance name and will not be monitored for "
                            "performance data", inter.Description,
                            inter.Index)

            # These virtual adapters should not be monitored as they are
            # like loopback, and are NOT available via perfmon
            if 'Microsoft Failover Cluster Virtual Adapter' in int_om.description:
                int_om.monitor = False

            mapInter.append(int_om)

        maps.append(RelationshipMap(
            relname="interfaces",
            compname="os",
            modname="Products.ZenModel.IpInterface",
            objmaps=mapInter))

        # Network Route Map
        mapRoute = []
        for route in res.netRoute:
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

        mapDisk = self.process_filesystems(device, res.fsDisk, log)

        maps.append(RelationshipMap(
            relname="filesystems",
            compname="os",
            modname="Products.ZenModel.FileSystem",
            objmaps=mapDisk))

        return maps

    def process_filesystems(self, device, fsDisk, log):
        # File System Map
        skipfsnames = getattr(device, 'zFileSystemMapIgnoreNames', None)
        skipfstypes = getattr(device, 'zFileSystemMapIgnoreTypes', None)

        mapDisk = []
        for disk in fsDisk:
            disk_om = ObjectMap()
            disk_om.mount = \
                "{driveletter} (Serial Number: {serialnumber}) - {name}" \
                .format(
                    driveletter=disk.Name,
                    serialnumber=disk.VolumeSerialNumber,
                    name=disk.VolumeName)

            #Check if drive description matches skip names
            if skipfsnames and re.search(skipfsnames, disk_om.mount):
                continue

            disk_om.drivetype = int(disk.DriveType)

            #Check for excluded drives
            if skipfstypes:
                # Get mapping of Windows Drive types to
                # Zenoss types for exclusion
                zentype = lookup_zendrivetype(disk_om.drivetype)
                for mapdisktype in zentype:
                    if mapdisktype in skipfstypes:
                        log.info(
                            "{drivename} drive's filesystem {filesystem}"
                            " has been excluded"
                            .format(drivename=disk.Name,
                                    filesystem=lookup_drivetype(
                                        disk_om.drivetype)))
                        break
                else:
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
                    disk_om.perfmonInstance = '\\LogicalDisk({0})'.format(disk.Name.rstrip('\\'))
                    mapDisk.append(disk_om)
        return mapDisk

    # builds a dictionary of perfmon instance paths for each network adapter
    # found in the WMI results query, keyed by the Index attribute
    #
    # the performon instance path is uses the following format:
    # \Network Interface(%instancename%#%index%)
    #
    # If multiple adapters are present with the same description then the #
    # sign followed by an index number for all additional instances beyond the
    # very first one. The index number does not correspond to the value found
    # in the Index or InterfaceIndex attribute directly, but instead is just a
    # simple counter for each instance of the same name found. The instances
    # are sorted by the InterfaceIndex or Index attribute to ensure that they
    # will receive the same calculated index value that perfmon uses.
    #
    # TOOD: this method can be made generic for all perfmon data that has
    # multiple instances and should be moved into WMIPlugin or some other
    # helper class.
    def buildPerfmonInstances(self, adapters, log):
        # don't bother with adapters without a description or interface index
        adapters = [a for a in adapters
                    if getattr(a, 'Description', None) is not None
                    and getattr(a, 'Index', None) is not None]

        def compareAdapters(a, b):
            n = cmp(a.Description, b.Description)
            if n == 0:
                n = cmp(a.Index, b.Index)
            return n
        adapters.sort(compareAdapters)

        # use the sorted interfaces to determine the perfmon unique instance
        # path
        instanceMap = {}
        index = 0
        prevDesc = None
        for adapter in adapters:
            # if we've encountered the same description multiple times in a row
            # then increment the index for this description for the additional
            # instances, otherwise build a perfmon-compatible description and
            # reset the index
            desc = adapter.Description
            if desc == prevDesc:
                index += 1
            else:
                index = 0
                prevDesc = standardizeInstance(desc)

            # only additional instances need the #index appended to the instance
            # name - the first item always appears without that qualifier
            if index > 0:
                perfmonInstance = '\\Network Interface(%s#%d)' % (prevDesc,
                                                                  index)
            else:
                perfmonInstance = '\\Network Interface(%s)' % prevDesc
            log.debug("%s=%s", adapter.Index, perfmonInstance)
            instanceMap[adapter.Index] = perfmonInstance

        return instanceMap
