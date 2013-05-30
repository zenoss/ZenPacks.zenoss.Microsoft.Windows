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

from Products.DataCollector.plugins.DataMaps \
    import ObjectMap, RelationshipMap
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from Products.ZenUtils.Utils import prepId

from ZenPacks.zenoss.Microsoft.Windows.txwinrm.collect \
    import ConnectionInfo, WinrmCollectClient, create_enum_info


class WinServices(PythonPlugin):

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        )

    WinRMQueries = [create_enum_info('select * from Win32_Service')]

    def collect(self, device, log):
        hostname = device.manageIp
        username = device.zWinUser
        auth_type = 'kerberos' if '@' in username else 'basic'
        password = device.zWinPassword
        scheme = 'http'
        port = 5985
        winrm = WinrmCollectClient()
        conn_info = ConnectionInfo(
            hostname, auth_type, username, password, scheme, port)
        results = winrm.do_collect(conn_info, self.WinRMQueries)
        return results

    def process(self, device, results, log):

        log.info('Modeler %s processing data for device %s',
            self.name(), device.id)

        osServices = results[self.WinRMQueries[0]]
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
