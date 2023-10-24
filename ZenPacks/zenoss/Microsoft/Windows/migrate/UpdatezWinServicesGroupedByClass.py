##############################################################################
#
# Copyright (C) Zenoss, Inc. 2023, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Update zWinServicesGroupedByClass with a default list of services
"""
import logging
log = logging.getLogger("zen.migrate")

# Platform Imports
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.Zuul.interfaces import ICatalogTool

# ZenPack Imports
from ZenPacks.zenoss.Microsoft.Windows.BaseDevice import BaseDevice
from ZenPacks.zenoss.Microsoft.Windows.Device import Device
from ZenPacks.zenoss.Microsoft.Windows.ClusterDevice import ClusterDevice


SERVICES_TO_ADD = ["BcastDVRUserService", "BluetoothUserService", "CDPUserSvc"
                   "CaptureService", "ConsentUxUserSvc",
                   "CredentialEnrollmentManagerUserSvc", "DevicePickerUserSvc",
                   "DevicesFlowUserSvc", "MessagingService", "OneSyncSvc", 
                   "PimIndexMaintenanceSvc", "PrintWorkflowUserSvc", "UdkUserSvc",
                   "UnistoreSvc", "UserDataSvc", "WpnUserService", "cbdhsvc"]


class UpdatezWinServicesGroupedByClass(ZenPackMigration):
    version = Version(3, 2, 0)

    def migrate(self, pack):
        log.info("Setting new default values %s to zWinServicesGroupedByClass", SERVICES_TO_ADD)
        dmd = pack.dmd

        org = dmd.Devices.getOrganizer('/Server/Microsoft')
        org.setZenProperty('zWinServicesGroupedByClass', SERVICES_TO_ADD)
        device_results = ICatalogTool(org).search(types=[BaseDevice, Device, ClusterDevice])
        for result in device_results:
            try:
                device = result.getObject()
            except Exception as e:
                log.warning("Error during migration: Unable to get Windows device with a reason - %s ", e)
                continue
            if hasattr(device, "zWinServicesGroupedByClass"):
                device.setZenProperty('zWinServicesGroupedByClass', SERVICES_TO_ADD)
