##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Windows Operating System Collection

"""
from twisted.internet.defer import DeferredList

import itertools
import re
import string

from pprint import pformat
from Products.DataCollector.plugins.DataMaps import MultiArgs, ObjectMap, RelationshipMap
from Products.ZenUtils.IpUtil import checkip, IpAddressError
from Products.ZenUtils.Utils import prepId
from Products.Zuul.utils import safe_hasattr

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import (
    addLocalLibPath,
    lookup_operstatus,
    )

addLocalLibPath()

from txwinrm.collect import WinrmCollectClient, create_enum_info, RequestError
from txwinrm.shell import create_single_shot_command


cluster_namespace = 'mscluster'
resource_uri = 'http://schemas.microsoft.com/wbem/wsman/1/wmi/root/{0}/*'.format(
    cluster_namespace)

ENUM_INFOS = dict(
    sysEnclosure=create_enum_info('select * from Win32_SystemEnclosure'),
    computerSystem=create_enum_info('select * from Win32_ComputerSystem'),
    operatingSystem=create_enum_info('select * from Win32_OperatingSystem'),
    netInt=create_enum_info('select * from Win32_NetworkAdapter'),
    netConf=create_enum_info('select * from Win32_NetworkAdapterConfiguration'),
    clusterInformation=create_enum_info(
        wql='select * from mscluster_cluster',
        resource_uri=resource_uri)
    )

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


class WinOS(WinRMPlugin):
    deviceProperties = WinRMPlugin.deviceProperties + (
        'zInterfaceMapIgnoreNames',
        )

    def collect(self, device, log):

        winrm = WinrmCollectClient()
        conn_info = self.conn_info(device)

        deferreds = []

        try:
            deferreds.append(winrm.do_collect(conn_info, ENUM_INFOS.values()))
            winrs = create_single_shot_command(conn_info)

        except RequestError as e:
            log.error(e[0])
            raise

        # Get registry information
        psRegistryGet = []
        # Base command line setup for powershell
        pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

        # Get information for network interfaces
        # This information will help define the TEAM/NLB components
        psRegistryGet.append("get-childitem \'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002bE10318}\'")
        psRegistryGet.append(" | foreach-object {get-itemproperty $_.pspath}")
        psRegistryGet.append(" | where-object {$_.flowcontrol -or $_.teammode -eq 0}")
        psRegistryGet.append(" | foreach-object {\'id=\', $_.pschildname, \';provider=\',")
        psRegistryGet.append("$_.providername, \';teamname=\', $_.oldfriendly, \';teammode=\',")
        psRegistryGet.append("$_.teammode, \';networkaddress=\', $_.networkaddress, \'|\'};")

        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(psRegistryGet))

        deferreds.append(winrs.run_command(command))

        d = DeferredList(deferreds, consumeErrors=True)
        return d

    def process(self, device, results, log):

        log.info('Modeler %s processing data for device %s',
                 self.name(), device.id)

        res = WinOSResult()

        try:
            osresults = results[0]
            regresults = ''.join(results[1][1].stdout).split('|')
        except (AttributeError):
            log.info('Failure collecting values on OS')
            pass

        for key, enum_info in ENUM_INFOS.iteritems():
            try:
                value = osresults[1][enum_info]
                if key in SINGLETON_KEYS:
                    value = value[0]
                setattr(res, key, value)
            except (KeyError, IndexError):
                pass

        maps = []

        # Registry Interface formatting
        regInterface = {}
        if regresults:
            for intFace in regresults:
                interfaceDict = {}
                try:
                    for keyvalues in intFace.split(';'):
                        key, value = keyvalues.split('=')
                        interfaceDict[key] = value
                    regInterface[int(interfaceDict['id'])] = interfaceDict
                except (KeyError, ValueError):
                    pass

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

        # Operating System Map
        res.operatingSystem.Caption = re.sub(r'\s*\S*Microsoft\S*\s*', '',
                                             res.operatingSystem.Caption)

        cs_om = ObjectMap()
        cs_om.title = res.computerSystem.DNSHostName
        cs_om.setHWProductKey = MultiArgs(res.computerSystem.Model,
                                          res.computerSystem.Manufacturer)
        osCaption = '{0} - {1}'.format(
            res.operatingSystem.Caption,
            res.operatingSystem.CSDVersion)

        cs_om.setOSProductKey = MultiArgs(osCaption,
                                          res.operatingSystem.Manufacturer)

        cs_om.snmpSysName = res.computerSystem.Name
        cs_om.snmpContact = res.computerSystem.PrimaryOwnerName
        cs_om.snmpDescr = res.computerSystem.Caption

        # Cluster Information

        try:
            clusterlist = []
            for cluster in res.clusterInformation:
                clusterlist.append(cluster.Name)
            cs_om.setClusterMachines = clusterlist
        except (AttributeError):
            pass

        maps.append(cs_om)

        # Interface Map
        mapInter = []
        # Virtual Team Interface Map
        mapTeamInter = []

        skipifregex = getattr(device, 'zInterfaceMapIgnoreNames', None)
        perfmonInstanceMap = self.buildPerfmonInstances(res.netConf, log)
        for inter in res.netInt:
            #Get the Network Configuration data for this interface

            #Merge registry data into object
            try:
                interfaceRegistry = regInterface[int(inter.DeviceID)]
                inter.TeamName = interfaceRegistry['teamname']
                inter.Provider = interfaceRegistry['provider']
                inter.TeamMode = interfaceRegistry['teammode']
                inter.TeamMAC = interfaceRegistry['networkaddress']

            except (KeyError):
                pass

            for intconf in res.netConf:
                if intconf.Index == inter.Index:
                    interconf = intconf
                    continue

            if inter.Description is not None:
                if skipifregex and re.match(skipifregex, inter.Description):
                    log.debug("Interface {intname} matched regex -- skipping"
                              .format(intname=inter.Description))
                    continue

            if interconf.MACAddress is None:
                continue

            if getattr(interconf, 'ServiceName', None) is not None:
                if 'netft' in interconf.ServiceName.lower():
                    # This is a Network Fault-Tolerant interface
                    # This should not be modeled as a local interface
                    continue

            ips = []

            if getattr(interconf, 'IPAddress', None) is not None:
                iplist = []
                masklist = []

                if isinstance(interconf.IPAddress, basestring):
                    iplist.append(interconf.IPAddress)
                else:
                    iplist = interconf.IPAddress

                if isinstance(interconf.IPSubnet, basestring):
                    masklist.append(interconf.IPSubnet)
                else:
                    masklist = interconf.IPSubnet

                for ip, mask in itertools.izip(iplist, masklist):
                    try:
                        checkip(ip)
                    except IpAddressError:
                        log.debug(
                            "Invalid IP Address {} encountered and skipped"
                            .format(ip))

                        continue

                    ips.append('{}/{}'.format(ip, self.maskToBits(mask)))

            int_om = ObjectMap()
            int_om.id = prepId(standardizeInstance(inter.Index + "-" + interconf.Description))

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

            # These physical interfaces should not be monitored as they are
            # in a Team configuration and will be monitored at the Team interface

            if getattr(inter, 'TeamName', None) is not None:
                if 'TEAM' in inter.TeamName:
                    int_om.monitor = False
                    int_om.teamname = inter.TeamName.split('-')[0].strip()

            # These interfaces are virtual TEAM interfaces
            if getattr(inter, 'TeamMode', None) is not None:
                if inter.TeamMode == '0':
                    log.debug('The TeamNic ID {0}'.format(int_om.id))
                    # Get the team name from the Description of the interface
                    int_om.teamname = interconf.Description.strip()
                    mapTeamInter.append(int_om)
                    continue
            mapInter.append(int_om)

        # Set supporting interfaces on TEAM nics
        for teamNic in mapTeamInter:
            members = []
            for nic in mapInter:
                if getattr(nic, 'teamname', None) is not None:
                    if nic.teamname == teamNic.teamname:
                        # This nic is a member of this team interface
                        members.append(nic.id)
            teamNic.setInterfaces = members

        maps.append(RelationshipMap(
            relname="interfaces",
            compname="os",
            modname="ZenPacks.zenoss.Microsoft.Windows.Interface",
            objmaps=mapInter))

        maps.append(RelationshipMap(
            relname="teaminterfaces",
            compname="os",
            modname="ZenPacks.zenoss.Microsoft.Windows.TeamInterface",
            objmaps=mapTeamInter))

        return maps

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
