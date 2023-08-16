##############################################################################
#
# Copyright (C) Zenoss, Inc. 2023, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema
from ZenPacks.zenoss.Microsoft.Windows.WinService import WinService
from Products.Zuul.interfaces import ICatalogTool


class ClusterResource(schema.ClusterResource):
    """
    class for Cluster Resource.
    """

    def is_winservice_disabled(self):
        if self.zWinClusterResourcesMonitoringDisabled:
            host_device = self.get_host_device()
            results = ICatalogTool(host_device).search(WinService)
            for result in results:
                try:
                    service = result.getObject()
                except Exception:
                    continue
                if self.winservice == service.id and service.startMode == "Disabled":
                    return True
                if service.caption == self.title and service.startMode == "Disabled":
                    return True
        return False

    def monitored(self):
        return not self.is_winservice_disabled()
