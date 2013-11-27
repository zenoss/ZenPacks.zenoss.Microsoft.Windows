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

    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        sysEnclosure = results.get('Win32_SystemEnclosure', (None,))[0]
        computerSystem = results.get('Win32_ComputerSystem', (None,))[0]
        operatingSystem = results.get('Win32_OperatingSystem', (None,))[0]
        clusterInformation = results.get('MSCluster', ())

        maps = []

        # Device Map
        device_om = ObjectMap()
        device_om.snmpSysName = computerSystem.Name
        device_om.snmpContact = computerSystem.PrimaryOwnerName
        device_om.snmpDescr = computerSystem.Caption

        # Cluster Information
        try:
            clusterlist = []
            for cluster in clusterInformation:
                clusterlist.append(cluster.Name)
            device_om.setClusterMachines = clusterlist
        except (AttributeError):
            pass

        maps.append(device_om)

        # Hardware Map
        hw_om = ObjectMap(compname='hw')
        hw_om.serialNumber = sysEnclosure.SerialNumber
        hw_om.tag = sysEnclosure.Tag
        hw_om.setProductKey = MultiArgs(
            computerSystem.Model,
            computerSystem.Manufacturer)

        if hasattr(operatingSystem, 'TotalVisibleMemorySize'):
            hw_om.totalMemory = 1024 * int(operatingSystem.TotalVisibleMemorySize)
        else:
            log.warn(
                "Win32_OperatingSystem query did not respond with "
                "TotalVisibleMemorySize: {0}"
                .format(pformat(sorted(vars(operatingSystem).keys()))))

        maps.append(hw_om)

        # Operating System Map
        os_om = ObjectMap(compname='os')
        os_om.totalSwap = int(operatingSystem.TotalVirtualMemorySize) * 1024

        operatingSystem.Caption = re.sub(
            r'\s*\S*Microsoft\S*\s*', '', operatingSystem.Caption)

        osCaption = '{} - {}'.format(
            operatingSystem.Caption,
            operatingSystem.CSDVersion)

        os_om.setProductKey = MultiArgs(
            osCaption,
            operatingSystem.Manufacturer)

        maps.append(os_om)

        return maps
