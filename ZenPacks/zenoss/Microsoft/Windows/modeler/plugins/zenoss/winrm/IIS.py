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
import re

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
    powershell_commands = {"version": "$iisversion = get-itemproperty HKLM:\SOFTWARE\Microsoft\InetStp\ | select versionstring;"
                           "Write-Host $iisversion.versionstring;"}

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

        def send_event(msg, severity, summary=None):
            self._send_event(msg,
                             device.id,
                             severity,
                             eventClass='/Status/Winrm',
                             key='IISSites',
                             summary=summary)

        output = yield orig.collect(device, log)

        if hasattr(orig, 'error_occurred'):
            send_event(orig.error_occurred, ZenEventClasses.Error)
            defer.returnValue(None)
        else:
            msg = 'Collection completed for {}'.format(device.id)
            send_event(msg, ZenEventClasses.Clear)

        version_results = output.get('version')
        if version_results and version_results.stdout:
            # version should be in 'Version x.x' format
            # 7 and above use the same namespace/query
            try:
                self.iis_version = re.match('Version (\d\.*\d*).*', version_results.stdout[0]).group(1)
            except (IndexError, AttributeError):
                if version_results.stdout:
                    log.debug("Malformed version information on {}: {}".format(device.id, version_results.stdout[0]))
                if version_results.stderr:
                    log.debug("Error retrieving IIS version on {}: {}".format(device.id, version_results.stderr))

        IIs7Sites = output.get('IIs7Site', ())
        if not self.iis_version:
            if IIs7Sites:
                self.iis_version = '7'
            else:
                self.iis_version = '6'

        for iisSite in IIs7Sites:
            name = iisSite.Name
            query = 'ASSOCIATORS OF {Site.Name="%s"} WHERE ResultClass=Application' % name
            result = yield self.run_query(conn_info, query, log)
            try:
                apps = result.values()[0][0]
                pool = apps.ApplicationPool
            except IndexError:
                pool = 'Unknown'
            iisSite.ApplicationPool = pool
        if not output.get('IIs7Site') and not output.get('IIsWebServerSetting'):
            msg = 'No IIS sites found on {}. Ensure that IIS Management Scripts'\
                ' and Tools have been installed.'.format(device.id)
            log.warn(msg)
            send_event(msg, ZenEventClasses.Warning, summary=msg)
        else:
            msg = "Found IIS sites on {}.".format(device.id)
            send_event(msg, ZenEventClasses.Clear)
        defer.returnValue(output)

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        device_om = ObjectMap()
        device_om.is_iis = False
        maps = [device_om]
        rm = self.relMap()
        if results.get('IIsWebServerSetting'):
            device_om.is_iis = True
            for iisSite in results.get('IIsWebServerSetting', ()):
                om = self.objectMap()
                om.id = self.prepId(iisSite.Name)
                if float(self.iis_version) == 6:
                    om.statusname = iisSite.Name
                else:
                    om.statusname = iisSite.ServerComment
                om.title = iisSite.ServerComment
                om.iis_version = self.iis_version
                om.sitename = iisSite.ServerComment  # Default Web Site
                if hasattr(iisSite, 'AppPoolId'):  # ZPS-5407 Can't get DefaultAppPool name
                    om.apppool = iisSite.AppPoolId
                elif hasattr(iisSite, 'ApplicationPool'): # ZPS-5407 Can't get DefaultAppPool name
                    om.apppool = iisSite.ApplicationPool

                for iisVirt in results.get('IIsWebVirtualDirSetting', ()):
                    if (iisVirt.Name == iisSite.Name + "/ROOT") or (iisVirt.Name == iisSite.Name + "/root"):
                        if iisVirt.AppPoolId is not None and iisVirt.AppPoolId != 'None': # ZPS-5407 Can't get DefaultAppPool name
                            om.apppool = iisVirt.AppPoolId

                rm.append(om)
        elif results.get('IIs7Site', False):
            device_om.is_iis = True
            for iisSite in results.get('IIs7Site', ()):
                try:
                    om = self.objectMap()
                    om.id = self.prepId(iisSite.Id)
                    om.title = om.statusname = om.sitename = iisSite.Name
                    om.iis_version = self.iis_version
                    om.apppool = iisSite.ApplicationPool
                    rm.append(om)
                except AttributeError:
                    pass

        maps.append(rm)
        return maps
