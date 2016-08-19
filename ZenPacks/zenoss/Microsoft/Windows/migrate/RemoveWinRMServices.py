##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""Remove Windows services.

ZEN-24347
winrmservices need to be removed as they are incompatible with the WinService
class.

"""

# Logging
import logging

# Zenoss Imports
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration

LOG = logging.getLogger('zen.MicrosoftWindows')


class RemoveWinRMServices(ZenPackMigration):
    version = Version(2, 6, 3)

    def migrate(self, pack):
        org = pack.dmd.Devices.getOrganizer('/Server/Microsoft')
        devices = org.getSubDevices()
        device_count = len(devices)
        if device_count:
            LOG.info('Removing incompatible Windows Services from {} device{}.'
                     .format(device_count, 's' if device_count > 1 else ''))
            for device in devices:
                device.os.removeRelation('winrmservices')
                device.os.buildRelations()
