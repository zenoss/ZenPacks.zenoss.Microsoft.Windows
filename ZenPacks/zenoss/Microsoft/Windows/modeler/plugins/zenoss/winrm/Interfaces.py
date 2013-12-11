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


_transTable = string.maketrans("#()/", "_[]_")


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
            "get-childitem 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002bE10318}'"
            " | foreach-object {get-itemproperty $_.pspath}"
            " | where-object {$_.flowcontrol -or $_.teammode -or $_.teamtype -eq 0}"
            " | foreach-object {'id=', $_.pschildname, ';provider=',"
            "$_.providername, ';teamname=', $_.oldfriendly, ';teammode=',"
            "$_.teammode, ';networkaddress=', $_.networkaddress,"
            "';netinterfaceid=', $_.netcfginstanceid,"
            "';altteamname=', $_.teamname, '|'};"
            ),
        'broadcomnic': (
            "get-childitem 'HKLM:\SYSTEM\CurrentControlSet\Services\Blfp\Parameters\Adapters'"
            " | foreach-object {get-itemproperty $_.pspath}"
            " | foreach-object {'id=', $_.pschildname, ';teamname=',"
            "$_.teamname, '|'};"
            ),
        }

    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        netInt = results.get('Win32_NetworkAdapter', ())
        netConf = results.get('Win32_NetworkAdapterConfiguration', ())

        regresults = results.get('registry')
        if regresults:
            regresults = ''.join(regresults.stdout).split('|')

        broadcomresults = results.get('broadcomnic')
        if broadcomresults:
            broadcomresults = ''.join(broadcomresults.stdout).split('|')

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
        perfmonInstanceMap = self.buildPerfmonInstances(netConf, log)

        for inter in netInt:
            #Get the Network Configuration data for this interface

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
                int_om.ifindex = inter.InterfaceIndex
            except (AttributeError, TypeError):
                int_om.ifindex = inter.Index

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
                    # Intel interface that is member of TEAM interface
                    int_om.teamname = inter.TeamName.split('-')[0].strip()
                    int_om.monitor = False
                else:
                    if inter.GUID in bdcDict:
                        # Broadcom interface that is member of TEAM interface
                        int_om.teamname = inter.TeamName
                        int_om.monitor = False

            # These interfaces are virtual TEAM interfaces
            if getattr(inter, 'TeamMode', None) is not None:
                if inter.TeamMode == '0':
                    log.debug('The TeamNic ID {0}'.format(int_om.id))
                    if not inter.TeamName:
                        # Get the team name from the Description of the interface
                        # This will be for Intel Team interfaces
                        int_om.teamname = interconf.Description.strip()
                    else:
                        # The Broadcom TeamName can be set early in the process
                        int_om.teamname = inter.TeamName
                        int_om.perfmonInstance = "\\network interface({0})".format(
                            "isatap." + inter.netinterfaceid)
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


def standardizeInstance(rawInstance):
    """
    Convert a raw perfmon instance name into a standardized one by replacing
    unfriendly characters with one that Windows expects.
    """
    return rawInstance.translate(_transTable)


def lookup_operstatus(value):
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
