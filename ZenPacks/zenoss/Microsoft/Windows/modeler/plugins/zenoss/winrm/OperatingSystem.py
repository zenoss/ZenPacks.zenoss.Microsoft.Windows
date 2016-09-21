##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
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

        sysEnclosure = results.get('Win32_SystemEnclosure', (None,))[0]
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
        try:
            device_om.snmpSysName = computerSystem.Name
            device_om.snmpContact = computerSystem.PrimaryOwnerName
            device_om.snmpDescr = computerSystem.Caption
        except AttributeError:
            log.warn('No results returned for Win32_ComputerSystem.  Check WMI namespace and DCOM permissions.')
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
        try:
            clusterlist = []
            for cluster in clusterInformation:
                clusterlist.append(cluster.Name + '.' + computerSystem.Domain)
            device_om.setClusterMachines = clusterlist
        except (AttributeError):
            pass

        # if domainrole is 4 or 5 then this is a DC
        # Standalone Workstation (0)
        # Member Workstation (1)
        # Standalone Server (2)
        # Member Server (3)
        # Backup Domain Controller (4)
        # Primary Domain Controller (5)
        if computerSystem.DomainRole in (BACKUPDC, PRIMARYDC):
            device_om.domain_controller = True
        else:
            device_om.domain_controller = False

        maps.append(device_om)

        # Hardware Map
        hw_om = ObjectMap(compname='hw')
        try:
            hw_om.serialNumber = operatingSystem.SerialNumber if operatingSystem else ''
        except AttributeError:
            log.warn('No results returned for Win32_OperatingSystem.  Check WMI namespace and DCOM permissions.')
        try:
            hw_om.tag = sysEnclosure.Tag
            hw_om.setProductKey = MultiArgs(
                computerSystem.Model,
                computerSystem.Manufacturer)
        except AttributeError:
            log.warn('No results returned for Win32_SystemEnclosure.  Check WMI namespace and DCOM permissions.')

        try:
            assert operatingSystem is not None
            hw_om.totalMemory = 1024 * int(operatingSystem.TotalVisibleMemorySize)
        except AttributeError:
            log.warn(
                "Win32_OperatingSystem query did not respond with "
                "TotalVisibleMemorySize: {0}"
                .format(pformat(sorted(vars(operatingSystem).keys()))))
        except AssertionError:
            log.warn('No results returned for Win32_OperatingSystem.  Check WMI namespace and DCOM permissions.')

        maps.append(hw_om)

        # Operating System Map
        os_om = ObjectMap(compname='os')
        try:
            os_om.totalSwap = int(operatingSystem.TotalVirtualMemorySize) * 1024

            operatingSystem.Caption = re.sub(
                r'\s*\S*Microsoft\S*\s*', '', operatingSystem.Caption)

            osCaption = '{} - {}'.format(
                operatingSystem.Caption,
                operatingSystem.CSDVersion)

            os_om.setProductKey = MultiArgs(
                osCaption,
                operatingSystem.Manufacturer)
        except AttributeError:
            pass
        maps.append(os_om)

        return maps
