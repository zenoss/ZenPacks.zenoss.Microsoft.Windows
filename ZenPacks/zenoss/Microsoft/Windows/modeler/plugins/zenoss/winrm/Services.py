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
from ZenPacks.zenoss.Microsoft.Windows.utils import save


class Services(WinRMPlugin):
    compname = 'os'
    relname = 'winservices'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.WinService'

    queries = {
        'Win32_Service': "SELECT * FROM Win32_Service",
        }

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        rm = self.relMap()

        for service in results.get('Win32_Service', ()):
            om = self.objectMap()
            om.id = self.prepId(service.Name)
            om.serviceName = service.Name
            om.caption = service.Caption
            om.setServiceClass = {'name':service.Name, 'description': service.Caption}
            om.pathName = service.PathName
            om.serviceType = service.ServiceType
            om.startMode = service.StartMode
            om.startName = service.StartName
            rm.append(om)

        return rm
