##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Windows Services

Models list of installed services by querying Win32_Service via WMI.
'''

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin


class Services(WinRMPlugin):
    compname = 'os'
    relname = 'winrmservices'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.WinService'

    queries = {
        'Win32_Service': "SELECT * FROM Win32_Service",
        }

    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        rm = self.relMap()

        for service in results.get('Win32_Service', ()):
            rm.append(self.objectMap({
                'id': self.prepId(service.Name),
                'title': service.Caption,
                'servicename': service.Name,
                'caption': service.Caption,
                'description': service.Description,
                'startmode': service.StartMode,
                'account': service.StartName,
                }))

        return rm
