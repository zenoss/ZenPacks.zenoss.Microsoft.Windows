##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Windows Operating System.

Models Windows operating system information by querying the following
classes:

    Win32_SystemEnclosure
    Win32_ComputerSystem
    Win32_OperatingSystem

Models cluster membership by querying MSCluster_MSCluster.
'''

import re

from pprint import pformat

from Products.DataCollector.plugins.DataMaps import MultiArgs, ObjectMap

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import save
PRIMARYDC = '5'
BACKUPDC = '4'
OS_DOMAIN_CONTROLLER = '2'


class OperatingSystem(WinRMPlugin):
    queries = {
        'Win32_SystemEnclosure': "SELECT * FROM Win32_SystemEnclosure",
        'Win32_ComputerSystem': "SELECT * FROM Win32_ComputerSystem",
        'Win32_OperatingSystem': "SELECT * FROM Win32_OperatingSystem",

        'MSCluster': {
            'query': 'SELECT * FROM mscluster_cluster',
            'namespace': 'mscluster',
        },
    }
    powershell_commands = dict(
        exchange_version=(
            'Get-Command exsetup |%{$_.Fileversioninfo.ProductVersion}'
        ),
    )

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        try:
            # assume valid results returned
            sysEnclosure = results.get('Win32_SystemEnclosure', None)[0]
        except Exception:
            # results contains Win32_SystemEnclosure as a key, but it's empty
            sysEnclosure = None
        computerSystem = results.get('Win32_ComputerSystem', (None,))[0]
        operatingSystem = results.get('Win32_OperatingSystem', (None,))[0]
        clusterInformation = results.get('MSCluster', ())
        exchange_version = results.get('exchange_version')

        if exchange_version:
            exchange_version = exchange_version.stdout[0][:2] if exchange_version.stdout else None

        if exchange_version:
            exchange_version = {'6': '2003', '8': '2010', '08': '2010', '14': '2010', '15': '2013'}.get(
                exchange_version
            )
        maps = []

        # Device Map
        device_om = ObjectMap()
        # safely get name, contact, desc
        sys_name = getattr(computerSystem, 'Name', None) or getattr(operatingSystem, 'CSName', None) or 'Unknown'
        device_om.snmpSysName = sys_name.strip()
        contact = getattr(computerSystem, 'PrimaryOwnerName', None) or getattr(operatingSystem, 'RegisteredUser', None) or 'Unknown'
        device_om.snmpContact = contact.strip()
        desc = getattr(computerSystem, 'Caption', None) or getattr(operatingSystem, 'Caption', None) or 'Unknown'
        device_om.snmpDescr = desc.strip()
        device_om.ip_and_hostname = self.get_ip_and_hostname(device.manageIp)

        # http://office.microsoft.com/en-001/outlook-help/determine-the-version-of-microsoft-exchange-server-my-account-connects-to-HA010117038.aspx
        if exchange_version:
            if exchange_version in ['2010', '2013']:
                device_om.msexchangeversion = 'MSExchange%sIS' % exchange_version
            else:
                # We use this attr to find the correct monitoring template
                device_om.msexchangeversion = 'MSExchangeInformationStore'
        else:
            device_om.msexchangeversion = ''
        # Cluster Information
        clusterlist = []
        for cluster in clusterInformation:
            clusterlist.append(getattr(cluster, 'Name', '') + '.' + getattr(computerSystem, 'Domain', ''))
        device_om.setClusterMachines = clusterlist

        # if domainrole is 4 or 5 then this is a DC
        # Standalone Workstation (0)
        # Member Workstation (1)
        # Standalone Server (2)
        # Member Server (3)
        # Backup Domain Controller (4)
        # Primary Domain Controller (5)
        device_om.domain_controller = False
        if getattr(computerSystem, 'DomainRole', '0') in (BACKUPDC, PRIMARYDC) or\
           getattr(operatingSystem, 'ProductType', '0') == OS_DOMAIN_CONTROLLER:
            device_om.domain_controller = True

        maps.append(device_om)

        # Hardware Map
        hw_om = ObjectMap(compname='hw')
        hw_om.serialNumber = getattr(operatingSystem, 'SerialNumber', '')
        hw_om.tag = getattr(sysEnclosure, 'Tag', 'Unknown')
        model = getattr(computerSystem, 'Model', 'Unknown')
        manufacturer = getattr(
            computerSystem, 'Manufacturer', getattr(
                operatingSystem, 'Manufacturer', 'Microsoft Corporation'))
        hw_om.setProductKey = MultiArgs(
            model,
            manufacturer)
        try:
            hw_om.totalMemory = 1024 * int(operatingSystem.TotalVisibleMemorySize)
        except AttributeError:
            log.warn(
                "Win32_OperatingSystem query did not respond with "
                "TotalVisibleMemorySize")

        maps.append(hw_om)

        # Operating System Map
        os_om = ObjectMap(compname='os')
        os_om.totalSwap = int(getattr(operatingSystem, 'TotalVirtualMemorySize', '0')) * 1024

        osCaption = getattr(operatingSystem, 'Caption', None) or 'Unknown'
        if osCaption and osCaption != 'Unknown':
            operatingSystem.Caption = re.sub(
                r'\s*\S*Microsoft\S*\s*', '', osCaption)

            osCaption = getattr(operatingSystem, 'Caption', 'Unknown')
        CSDVersion = getattr(operatingSystem, 'CSDVersion', 'Unknown')
        if CSDVersion:
            osCaption += ' - {}'.format(CSDVersion)

        os_om.setProductKey = MultiArgs(
            osCaption,
            getattr(operatingSystem, 'Manufacturer', 'Microsoft Corporation'))
        maps.append(os_om)

        return maps
