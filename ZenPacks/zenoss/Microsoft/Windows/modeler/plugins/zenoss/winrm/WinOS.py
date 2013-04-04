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

from twisted.internet import reactor
from twisted.web.client import Agent
from twisted.internet.defer import DeferredList
from twisted.internet.protocol import Protocol

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

        maps = []

        #Hardware Map
        hw_om = ObjectMap(compname='hw')
        hw_om.serialNumber = sysEnclosure.SerialNumber
        hw_om.tag = sysEnclosure.Tag
        hw_om.totalMemory = computerSystem.TotalPhysicalMemory

        maps.append(hw_om)

        #Computer System Map
        cs_om = ObjectMap()
        cs_om.title = computerSystem.DNSHostName
        cs_om.snmpSysName = computerSystem.Name
        cs_om.snmpContact = computerSystem.PrimaryOwnerName
        cs_om.snmpDescr = computerSystem.Caption

        maps.append(cs_om)

        return maps
