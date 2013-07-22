##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Windows Internet Information Services Collection

"""

from Products.DataCollector.plugins.DataMaps \
    import ObjectMap, RelationshipMap
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from Products.ZenUtils.Utils import prepId
from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath

addLocalLibPath()

from txwinrm.collect import ConnectionInfo, WinrmCollectClient, create_enum_info


class WinIIS(PythonPlugin):

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        )

    enum_info = create_enum_info(wql='select * from IIsWebServerSetting',
        resource_uri='http://schemas.microsoft.com/wbem/wsman/1/wmi/root/cimv2')

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
        results = winrm.do_collect(conn_info, [self.enum_info])
        return results

    def process(self, device, results, log):

        log.info('Modeler %s processing data for device %s',
                 self.name(), device.id)

        iisSites = results[self.enum_info]
        maps = []
        siteMap = []
        for site in iisSites:
            om = ObjectMap()
            om.id = prepId(site.Name)
            om.title = site.ServerComment
            om.sitename = site.ServerComment
            om.caption = site.Caption
            om.apppool = site.AppPoolId

            siteMap.append(om)

        maps.append(RelationshipMap(
            relname="winrmiis",
            compname="os",
            modname="ZenPacks.zenoss.Microsoft.Windows.WinIIS",
            objmaps=siteMap))

        return maps
