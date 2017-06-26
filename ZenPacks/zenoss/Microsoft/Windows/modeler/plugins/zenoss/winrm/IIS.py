##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2017, all rights reserved.
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

from Products.ZenEvents import ZenEventClasses
from Products.DataCollector.plugins.DataMaps import ObjectMap
from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import save
from txwinrm.collect import create_enum_info
from txwinrm.WinRMClient import EnumerateClient
from twisted.internet import defer


class IIS(WinRMPlugin):
    compname = 'os'
    relname = 'winrmiis'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.WinIIS'

    winrm = None
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

    iis_version = None
    powershell_commands = {"version": "(Get-Command $env:SystemRoot\system32\inetsrv\InetMgr.exe).Version.Major"}

    @defer.inlineCallbacks
    def run_query(self, conn_info, wql, log):
        self.winrm = EnumerateClient(conn_info)
        wql = create_enum_info(wql=wql, resource_uri=self.uri)
        result = yield self.winrm.do_collect([wql])
        defer.returnValue(result)

    @defer.inlineCallbacks
    def collect(self, device, log):
        orig = WinRMPlugin()
        orig.queries = self.queries
        orig.powershell_commands = self.powershell_commands
        conn_info = self.conn_info(device)
        output = yield orig.collect(device, log)

        version_results = output.get('version')
        if version_results and version_results.stdout:
            try:
                self.iis_version = int(version_results.stdout[0])
            except ValueError, IndexError:
                log.debug('Incorrect IIS data received: {}'.format(version_results.stdout))

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
        if not output:
            msg = 'No IIS sites found on {}. Ensure that IIS Management Scripts'\
                ' and Tools have been installed.'.format(device.id)
            log.warn(msg)
            self._send_event(msg,
                             device.id,
                             ZenEventClasses.Warning,
                             eventClass='/Status/Winrm',
                             key='IISSites', summary=msg)
        else:
            msg = "Found IIS sites on {}.".format(device.id)
            self._send_event(msg, device.id, ZenEventClasses.Clear, eventClass='/Status/Winrm', key='IISSites')
        defer.returnValue(output)

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        device_om = ObjectMap()
        device_om.is_iis = True
        maps = [device_om]
        rm = self.relMap()
        if results.get('IIsWebServerSetting'):
            for iisSite in results.get('IIsWebServerSetting', ()):
                om = self.objectMap()
                om.id = self.prepId(iisSite.Name)
                om.statusname = iisSite.Name
                om.title = iisSite.ServerComment
                om.iis_version = self.iis_version or 6
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
                    om.iis_version = self.iis_version or 7
                    if iisSite.ServerAutoStart == 'false':
                        om.status = 'Stopped'
                    else:
                        om.status = 'Running'
                    om.apppool = iisSite.ApplicationPool
                    rm.append(om)
                except AttributeError:
                    pass

        maps.append(rm)
        return maps
