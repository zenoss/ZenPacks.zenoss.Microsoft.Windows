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
from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath

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
        #import pdb; pdb.set_trace()

        sysEnclosure = results['select * from Win32_SystemEnclosure'][0]
        computerSystem = results['select * from Win32_ComputerSystem'][0]
        operatingSystem = results['select * from Win32_OperatingSystem'][0]

        maps = []

        #Hardware Map
        hw_om = ObjectMap(compname='hw')
        hw_om.serialNumber = sysEnclosure.SerialNumber
        hw_om.tag = sysEnclosure.Tag
        hw_om.totalMemory = computerSystem.TotalPhysicalMemory

        maps.append(hw_om)

        #Computer System Map

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

        return maps
