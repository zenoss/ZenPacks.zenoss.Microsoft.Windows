##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Windows Internet Information Services (IIS).

Models IIS sites by querying the following classes in the MicrosoftIISv2
namespace:

    IIsWebVirtualDirSetting
    IIsWebServerSetting
'''

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import save
from txwinrm.collect import WinrmCollectClient, create_enum_info
from twisted.internet import defer


class IIS(WinRMPlugin):
    compname = 'os'
    relname = 'winrmiis'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.WinIIS'

    winrm = WinrmCollectClient()
    uri = 'http://schemas.microsoft.com/wbem/wsman/1/wmi/root/webadministration/*'

    queries = {
        'IIsWebServerSetting': {
            'query': "SELECT * FROM IIsWebServerSetting",
            'namespace': 'microsoftiisv2',
            },

        'IIsWebVirtualDirSetting': {
            'query': "SELECT * FROM IIsWebVirtualDirSetting",
            'namespace': 'microsoftiisv2',
            },

        'IIs7Site': {
            'query': "SELECT Name, Id, ServerAutoStart  FROM Site",
            'namespace': 'WebAdministration',
            },
    }

    @defer.inlineCallbacks
    def run_query(self, conn_info, wql, log):
        wql = create_enum_info(wql=wql, resource_uri=self.uri)
        result = yield self.winrm.do_collect(conn_info, [wql])
        defer.returnValue(result)

    @defer.inlineCallbacks
    def collect(self, device, log):
        orig = WinRMPlugin()
        orig.queries = self.queries
        conn_info = self.conn_info(device)
        output = yield orig.collect(device, log)
        for iisSite in output.get('IIs7Site', ()):
            name = iisSite.Name
            query = 'ASSOCIATORS OF {Site.Name="%s"} WHERE ResultClass=Application' % name
            result = yield self.run_query(conn_info, query, log)
            try:
                apps = result.values()[0][0]
                pool = apps.ApplicationPool
            except IndexError:
                pool = 'Unknown'
            iisSite.ApplicationPool = pool
        defer.returnValue(output)

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        rm = self.relMap()
        if results.get('IIsWebServerSetting'):
            for iisSite in results.get('IIsWebServerSetting', ()):
                om = self.objectMap()
                om.id = self.prepId(iisSite.Name)
                om.statusname = iisSite.Name
                om.title = iisSite.ServerComment
                om.iis_version = 6
                om.sitename = iisSite.ServerComment  # Default Web Site
                if iisSite.ServerAutoStart == 'false':
                    om.status = 'Stopped'
                else:
                    om.status = 'Running'

                for iisVirt in results.get('IIsWebVirtualDirSetting', ()):
                    if (iisVirt.Name == iisSite.Name + "/ROOT") or (iisVirt.Name == iisSite.Name + "/root"):
                        om.apppool = iisVirt.AppPoolId

                rm.append(om)
        else:
            for iisSite in results.get('IIs7Site', ()):
                try:
                    om = self.objectMap()
                    om.id = self.prepId(iisSite.Id)
                    om.title = om.statusname = om.sitename = iisSite.Name
                    om.iis_version = 7
                    if iisSite.ServerAutoStart == 'false':
                        om.status = 'Stopped'
                    else:
                        om.status = 'Running'
                    om.apppool = iisSite.ApplicationPool
                    rm.append(om)
                except AttributeError:
                    pass

        return rm
