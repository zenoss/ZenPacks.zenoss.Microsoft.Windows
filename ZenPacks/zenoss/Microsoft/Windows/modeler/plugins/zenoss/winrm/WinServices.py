##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Windows Services Collection

"""
import logging
import re

from Products.DataCollector.plugins.DataMaps \
    import MultiArgs, ObjectMap, RelationshipMap
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from Products.ZenUtils.Utils import prepId

from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath

addLocalLibPath()

from txwinrm.collect import WinrmCollectClient


class WinServices(PythonPlugin):

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        )

    WinRMQueries = [
        'select * from Win32_Service',
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

        osServices = results['select * from Win32_Service']
        maps = []
        serviceMap = []
        for service in osServices:
            om = ObjectMap()
            om.id = prepId(service.Name)
            om.title = service.Name
            om.servicename = service.Name
            om.caption = service.Caption
            om.description = service.Description
            om.startmode = service.StartMode
            om.account = service.StartName
            om.state = service.State

            serviceMap.append(om)

        maps.append(RelationshipMap(
            relname="winrmservices",
            compname="os",
            modname="ZenPacks.zenoss.Microsoft.Windows.WinService",
            objmaps=serviceMap))

        return maps
