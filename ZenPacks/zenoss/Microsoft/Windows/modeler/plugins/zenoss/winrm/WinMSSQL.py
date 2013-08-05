##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Windows MS SQL Server Collection

Namespace: Microsoft.SqlServer.Management.Smo.Wmi 

"""

from Products.DataCollector.plugins.DataMaps \
    import ObjectMap, RelationshipMap
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from Products.ZenUtils.Utils import prepId
from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath

addLocalLibPath()

from txwinrm.collect import ConnectionInfo, WinrmCollectClient


class WinMSSQL(PythonPlugin):

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        )

    WinRMQueries = [
        'select * from ',
        ]

    def collect(self, device, log):
        hostname = device.manageIp
        username = device.zWinUser
        auth_type = 'kerberos' if '@' in username else 'basic'
        password = device.zWinPassword
        scheme = 'http'
        port = 5985
        connectiontype = 'Keep-Alive'

        winrm = WinrmCollectClient()
        conn_info = ConnectionInfo(
            hostname,
            auth_type,
            username,
            password,
            scheme,
            port,
            connectiontype)
        results = winrm.do_collect(conn_info, self.WinRMQueries)
        return results

    def process(self, device, results, log):

        log.info('Modeler %s processing data for device %s',
            self.name(), device.id)

        mssqlServer = results['select * from ']
        maps = []
        siteMap = []
        for db in mssqlServer:
            om = ObjectMap()
            om.id = prepId(db.Name)
            om.title = db.ServerComment
            om.sitename = db.ServerComment
            om.caption = db.Caption
            om.apppool = site.AppPoolId

            siteMap.append(om)

        maps.append(RelationshipMap(
            relname="winrmiis",
            compname="os",
            modname="ZenPacks.zenoss.Microsoft.Windows.WinIIS",
            objmaps=siteMap))

        return maps
