##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Windows Network Interfaces.

Models network interfaces by querying Win32_NetworkAdapter and
Win32_NetworkAdapterConfiguration via WMI, and gathering teaming
information from the registry using PowerShell.
'''

import itertools
import re
import string

from Products.ZenUtils.IpUtil import checkip, IpAddressError

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import save


_transTable = string.maketrans("#()/", "_[]_")


# Windows Server 2003 and Windows XP has no true/false status field
# for enabled/disabled states. This statuses used to determine if
# interface is enabled:
ENABLED_NC_STATUSES = [
    '1',  # Connecting
    '2',  # Connected
    '8',  # Authenticating
    '9',  # Authentication succeeded
    '10',  # Authentication failed
    '11',  # Invalid address
    '12',  # Credentials required
]

# Availability instead of Operational Status
AVAILABILITY = {
    '1': 4,  # Other
    '2': 4,  # Unknown
    '3': 1,  # Running or Full Power
    '4': 1,  # Warning
    '5': 3,  # In Test
    '6': 4,  # Not Applicable
    '7': 2,  # Power Off
    '8': 2,  # Off Line
    '9': 2,  # Off Duty
    '10': 1,  # Degraded
    '11': 6,  # Not Installed
    '12': 6,  # Install Error
    '13': 4,  # Power Save - Unknown
    '14': 1,  # Power Save - Lower Power Mode
    '15': 2,  # Power Save - Standby
    '16': 2,  # Power Cycle
    '17': 1,  # Warning
}


class Interfaces(WinRMPlugin):
    compname = 'os'
    relname = 'interfaces'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.Interface'

    deviceProperties = WinRMPlugin.deviceProperties + (
        'zInterfaceMapIgnoreDescriptions',
        'zInterfaceMapIgnoreNames',
        'zInterfaceMapIgnoreTypes',
        )

    queries = {
        'Win32_NetworkAdapter': "SELECT * FROM Win32_NetworkAdapter",
        'Win32_NetworkAdapterConfiguration': "SELECT * FROM Win32_NetworkAdapterConfiguration",
        }

    '''
    Team NIC information is collected per device type from the registry.
    Each vendor will have a differnt location in the registry to store the member
    nic information. This version of the Windows ZP support the following NIC
    teaming software.

    Intel
    Broadcom

    '''
    powershell_commands = {
        'registry': (
            "get-childitem -ea silentlycontinue 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002bE10318}'"
            " | foreach-object {get-itemproperty $_.pspath}"
            " | where-object {$_.flowcontrol -or $_.teammode -or $_.teamtype -eq 0}"
            " | foreach-object {'id=', $_.pschildname, ';provider=',"
            "$_.providername, ';teamname=', $_.oldfriendly, ';teammode=',"
            "$_.teammode, ';networkaddress=', $_.networkaddress,"
            "';netinterfaceid=', $_.netcfginstanceid,"
            "';altteamname=', $_.teamname, '|'};"
        ),
        'broadcomnic': (
            "get-childitem -ea silentlycontinue 'HKLM:\SYSTEM\CurrentControlSet\Services\Blfp\Parameters\Adapters'"
            " | foreach-object {get-itemproperty $_.pspath}"
            " | foreach-object {'id=', $_.pschildname, ';teamname=',"
            "$_.teamname, '|'};"
        ),
        'counters2012': (
            ' '.join('''$ver2012 = (Get-WmiObject win32_OperatingSystem).Name -like '*2012*';
            function replace_unallowed($s)
            {$s.replace('(', '[').replace(')', ']').replace('#', '_').replace('\\', '_').replace('/', '_').toLower()}
            if($ver2012){
            (Get-Counter '\Network Adapter(*)\*').CounterSamples |
                % {$_.InstanceName} | gu | % {
                foreach($na in (Get-WmiObject MSFT_NetAdapter -Namespace 'root/StandardCimv2')) {
                    if($_ -eq (replace_unallowed $na.InterfaceDescription) -or $_ -like 'isatap.' + "$($na.DeviceID)") {
                        $na.DeviceID, ':', $_, '|'
            }}}}'''.split())
        ),
        'win32_pnpentity': (
            "$Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(4096, 25);"
            "$interfaces = (get-wmiobject -query 'select * from win32_networkadapter'); foreach ($interface in $interfaces) {"
            "$query = 'ASSOCIATORS OF {Win32_NetworkAdapter.DeviceID='+$interface.DeviceID+'} WHERE ResultClass=Win32_PnPEntity';"
            "get-wmiobject -query $query}"
        )
    }

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        netInt = results.get('Win32_NetworkAdapter', ())
        netConf = results.get('Win32_NetworkAdapterConfiguration', ())
        win32_pnpentities = results.get('win32_pnpentity', None)

        # Actual instance names should be pulled in from the Win32_PnPEntity class
        if win32_pnpentities and win32_pnpentities.stdout:
            pnpentities = {}
            pnpentity = {}
            for line in win32_pnpentities.stdout:
                k, v = line.split(':', 1)
                # __GENUS marks the beginning of a win32_pnpentity class
                if k.strip() == '__GENUS':
                    if 'PNPDeviceID' in pnpentity.keys():
                        pnpentities[pnpentity['PNPDeviceID']] = pnpentity
                        pnpentity = {}
                pnpentity[k.strip()] = v.strip()
            # add in the last one
            pnpentities[pnpentity['PNPDeviceID']] = pnpentity
        else:
            pnpentities = None

        regresults = results.get('registry')
        if regresults:
            regresults = ''.join(regresults.stdout).split('|')

        broadcomresults = results.get('broadcomnic')
        if broadcomresults:
            broadcomresults = ''.join(broadcomresults.stdout).split('|')

        # Performance Counters for Windows 2012
        counters = self.sanitize_counters(results.get('counters2012'))

        # Interface Map
        mapInter = []

        # Virtual Team Interface Map
        mapTeamInter = []

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

        # Broadcom member nic map
        bdcDict = {}
        if broadcomresults:
            for memberNic in broadcomresults:
                memberDict = {}
                try:
                    for keyvalues in memberNic.split(';'):
                        key, value = keyvalues.split('=')
                        memberDict[key] = value
                    bdcDict[memberDict['id']] = memberDict['teamname']
                except (KeyError, ValueError):
                    pass
        perfmonInstanceMap = self.buildPerfmonInstances(netConf, log, counters, pnpentities, netInt)

        for inter in netInt:
            # Get the Network Configuration data for this interface

            # Merge broadcom NIC Team information into object
            try:
                inter.TeamName = bdcDict[inter.GUID]
            except (KeyError, AttributeError):
                pass

            # Merge registry data for Team Interface into object
            try:
                interfaceRegistry = regInterface[int(inter.DeviceID)]
                if not interfaceRegistry['teamname']:
                    if not interfaceRegistry['altteamname']:
                        inter.TeamName = inter.NetConnectionID
                    else:
                        inter.TeamMode = '0'
                        inter.TeamName = interfaceRegistry['altteamname']
                    inter.netinterfaceid = interfaceRegistry['netinterfaceid']
                else:
                    inter.TeamName = interfaceRegistry['teamname']
                    inter.TeamMode = interfaceRegistry['teammode']

                inter.Provider = interfaceRegistry['provider']
                inter.InterfaceID = interfaceRegistry['netinterfaceid']
                inter.TeamMAC = interfaceRegistry['networkaddress']

            except (KeyError):
                pass
            for intconf in netConf:
                if intconf.InterfaceIndex == inter.InterfaceIndex:
                    interconf = intconf
                    break
            else:
                log.warn(
                    "No configuration found for %s on %s",
                    inter.Description, device.id)

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

            int_om = self.objectMap()
            int_om.id = self.prepId(
                standardizeInstance(
                    inter.Index + "-" + interconf.Description))

            int_om.title = interconf.Description
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
                int_om.speed = int(inter.Speed)
            else:
                int_om.speed = 0

            int_om.duplex = 0
            int_om.type = inter.AdapterType

            try:
                int_om.adminStatus = 0
                # ZEN-15493: workaround LPU cannot access NetEnabled property
                # Check IPEnabled property of configuration
                if inter.NetEnabled is None:
                    if inter.NetConnectionStatus in ENABLED_NC_STATUSES:
                        int_om.adminStatus = 1
                    elif inter.NetConnectionStatus is None:
                        int_om.adminStatus = int(lookup_adminstatus(interconf.IPEnabled))
                else:
                    int_om.adminStatus = int(lookup_adminstatus(inter.NetEnabled))
            except (AttributeError):
                # Workaround for 2003 / XP
                if inter.NetConnectionStatus in ENABLED_NC_STATUSES:
                    int_om.adminStatus = 1

            try:
                int_om.ifindex = inter.InterfaceIndex
            except (AttributeError, TypeError):
                int_om.ifindex = inter.Index

            if inter.Index in perfmonInstanceMap:
                # only physical adapters will have perfmon data
                # 2003 does not have the PhysicalAdapter property
                if getattr(inter, 'PhysicalAdapter', 'true').lower() == 'true':
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
                    # Intel interface that is member of TEAM interface
                    int_om.teamname = inter.TeamName.split('-')[0].strip()
                    int_om.monitor = False
                else:
                    if hasattr(inter, 'GUID') and (inter.GUID in bdcDict):
                        # Broadcom interface that is member of TEAM interface
                        int_om.teamname = inter.TeamName
                        int_om.monitor = False

            # These interfaces are virtual TEAM interfaces
            if getattr(inter, 'TeamMode', None) is not None:
                if inter.TeamMode == '0':
                    if counters and counters.get(inter.netinterfaceid):
                        pass
                    else:
                        int_om.perfmonInstance = "\\network interface({0})".format(
                            "isatap." + inter.netinterfaceid)
                    log.debug('The TeamNic ID {0}'.format(int_om.id))
                    if not inter.TeamName:
                        # Get the team name from the Description of the interface
                        # This will be for Intel Team interfaces
                        int_om.teamname = interconf.Description.strip()
                    else:
                        # The Broadcom TeamName can be set early in the process
                        int_om.teamname = inter.TeamName
                    int_om.modname = 'ZenPacks.zenoss.Microsoft.Windows.TeamInterface'
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

        rm = self.relMap()
        rm.maps.extend(mapInter + mapTeamInter)

        # Filter interfaces using filtering zProperties.
        rm.maps = list(filter_maps(rm.maps, device, log))

        return rm

    def sanitize_counters(self, counters):
        """
        Converts raw windows 2012 counters to dictionary
        """
        if not counters:
            return None

        res = {}
        for elem in ''.join(counters.stdout).split('|')[:-1]:
            k, v = elem.split(':')[0], elem.split(':')[1]
            if k in res:
                # on Windows 2012R2 interfaces with #N has duplicate
                # counters, one with normal name and other like isatap.{...}
                if not 'isatap' in v:
                    res[k] = v
            else:
                res[k] = v
        return res

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
    def buildPerfmonInstances(self, adapters, log, counters=None, pnpentities=None, netInt=None):
        # don't bother with adapters without a description or interface index
        adapters = [a for a in adapters
                    if getattr(a, 'Description', None) is not None
                    and getattr(a, 'Index', None) is not None]

        def compareAdapters(a, b):
            n = cmp(a.Description, b.Description)
            if n == 0:
                n = cmp(int(a.Index), int(b.Index))
            return n
        adapters.sort(compareAdapters)

        # use the sorted interfaces to determine the perfmon unique instance
        # path
        instanceMap = {}
        prevDesc = {}
        for adapter in adapters:
            # comparison Performance Counters with existing Network Adapters for Windows 2012
            if counters and counters.get(adapter.SettingID):
                instanceMap[adapter.Index] = '\\Network Adapter({})'.format(
                    counters.get(adapter.SettingID)
                )
            else:
                # if we've encountered the same description multiple times in a row
                # then increment the index for this description for the additional
                # instances, otherwise build a perfmon-compatible description and
                # reset the index
                # the real counter instance name is found in the win32_pnpentity class
                # we have to cross reference the interface index to get to the pnpdeviceid
                # if the Name is empty then just use the adapter description
                desc = None
                if pnpentities and netInt:
                    for intfc in netInt:
                        if intfc.InterfaceIndex == adapter.InterfaceIndex:
                            try:
                                desc = pnpentities[intfc.PNPDeviceID]['Name']
                            except Exception:
                                pass
                            break
                if not desc:
                    desc = adapter.Description
                desc = standardizeInstance(desc)
                if desc in prevDesc.keys():
                    prevDesc[desc] += 1
                else:
                    prevDesc[desc] = 0

                # only additional instances need the #index appended to the instance
                # name - the first item always appears without that qualifier
                if prevDesc[desc] > 0:
                    perfmonInstance = '\\Network Interface(%s#%d)' % (desc,
                                                                      prevDesc[desc])
                else:
                    perfmonInstance = '\\Network Interface(%s)' % desc
                instanceMap[adapter.Index] = perfmonInstance
            log.debug("%s=%s", adapter.Index, instanceMap[adapter.Index])
        return instanceMap


def standardizeInstance(rawInstance):
    """
    Convert a raw perfmon instance name into a standardized one by replacing
    unfriendly characters with one that Windows expects.
    """
    return rawInstance.translate(_transTable)


def lookup_adminstatus(value):
    """
    return number value for adminstatus.  used to determine monitoring.
    """
    if value == 'true':
        return 1
    else:
        return 2


def filter_maps(objectmaps, device, log):
    '''
    Generate filtered objectmaps given device configuration.
    '''
    ignore_descrs = getattr(device, 'zInterfaceMapIgnoreDescriptions', None)
    if ignore_descrs:
        ignore_descrs_search = re.compile(ignore_descrs).search

    ignore_names = getattr(device, 'zInterfaceMapIgnoreNames', None)
    if ignore_names:
        ignore_names_search = re.compile(ignore_names).search

    ignore_types = getattr(device, 'zInterfaceMapIgnoreTypes', None)
    if ignore_types:
        ignore_types_search = re.compile(ignore_types).search

    for om in objectmaps:
        name = om.interfaceName

        if ignore_descrs and ignore_descrs_search(om.description):
            log.info(
                "Ignoring %s on %s because it matches "
                "zInterfaceMapIgnoreDescriptions",
                name, device.id)

        elif ignore_names and ignore_names_search(name):
            log.info(
                "Ignoring %s on %s because it matches "
                "zInterfaceMapIgnoreNames",
                name, device.id)

        elif ignore_types and ignore_types_search(om.type):
            log.info(
                "Ignoring %s on %s because it matches "
                "zInterfaceMapIgnoreTypes",
                name, device.id)

        else:
            yield om
