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
from Products.ZenUtils.Utils import prepId

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils \
    import addLocalLibPath

addLocalLibPath()

from txwinrm.collect \
    import ConnectionInfo, WinrmCollectClient, create_enum_info, RequestError


class WinServices(WinRMPlugin):

    WinRMQueries = [create_enum_info('select * from Win32_Service')]

    def collect(self, device, log):
        winrm = WinrmCollectClient()
        conn_info = self.conn_info(device)

        try:
            results = winrm.do_collect(conn_info, self.WinRMQueries)
        except RequestError as e:
            log.error(e[0])
            raise
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
