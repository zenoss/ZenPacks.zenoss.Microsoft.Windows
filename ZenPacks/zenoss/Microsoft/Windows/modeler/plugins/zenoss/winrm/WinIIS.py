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

namespace = 'microsoftiisv2'
resource_uri = 'http://schemas.microsoft.com/wbem/wsman/1/wmi/root/{0}/*'.format(namespace)

ENUM_INFOS = dict(
    iisVirtuals=create_enum_info(wql='select * from IIsWebVirtualDirSetting',
        resource_uri=resource_uri),
    iisSites=create_enum_info(wql='select * from IIsWebServerSetting',
        resource_uri=resource_uri))


SINGLETON_KEYS = []


class WinIISResult(object):
    pass


class WinIIS(PythonPlugin):

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        'zWinRMPort',
        )

    def collect(self, device, log):
        hostname = device.manageIp
        username = device.zWinUser
        auth_type = 'kerberos' if '@' in username else 'basic'
        password = device.zWinPassword
        scheme = 'http'
        port = int(device.zWinRMPort)
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

        results = winrm.do_collect(conn_info, ENUM_INFOS.values())

        return results

    def process(self, device, results, log):
        log.info('Modeler %s processing data for device %s',
                 self.name(), device.id)

        res = WinIISResult()
        for key, enum_info in ENUM_INFOS.iteritems():
            value = results[enum_info]
            if key in SINGLETON_KEYS:
                value = value[0]
            setattr(res, key, value)

        maps = []
        siteMap = []

        for iisSite in res.iisSites:
            om = ObjectMap()
            om.id = prepId(iisSite.Name)
            om.statusname = iisSite.Name
            om.title = iisSite.ServerComment
            om.sitename = iisSite.ServerComment
            if iisSite.ServerAutoStart == 'false':
                om.status = 'Stopped'
            else:
                om.status = 'Running'

            for iisVirt in res.iisVirtuals:
                if iisVirt.Name == iisSite.Name + "/root":
                    om.apppool = iisVirt.AppPoolId
            siteMap.append(om)

        maps.append(RelationshipMap(
            relname="winrmiis",
            compname="os",
            modname="ZenPacks.zenoss.Microsoft.Windows.WinIIS",
            objmaps=siteMap))

        return maps
