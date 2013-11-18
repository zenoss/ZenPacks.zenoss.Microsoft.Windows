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


class IIS(WinRMPlugin):
    compname = 'os'
    relname = 'winrmiis'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.WinIIS'

    queries = {
        'IIsWebServerSetting': {
            'query': "SELECT * FROM IIsWebServerSetting",
            'namespace': 'microsoftiisv2',
            },

        'IIsWebVirtualDirSetting': {
            'query': "SELECT * FROM IIsWebVirtualDirSetting",
            'namespace': 'microsoftiisv2',
            },
        }

    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        rm = self.relMap()

        for iisSite in results.get('IIsWebServerSetting', ()):
            om = self.objectMap()
            om.id = self.prepId(iisSite.Name)
            om.statusname = iisSite.Name
            om.title = iisSite.ServerComment
            om.sitename = iisSite.ServerComment
            if iisSite.ServerAutoStart == 'false':
                om.status = 'Stopped'
            else:
                om.status = 'Running'

            for iisVirt in results.get('IIsWebVirtualDirSetting', ()):
                if iisVirt.Name == iisSite.Name + "/root":
                    om.apppool = iisVirt.AppPoolId

            rm.append(om)

        return rm
