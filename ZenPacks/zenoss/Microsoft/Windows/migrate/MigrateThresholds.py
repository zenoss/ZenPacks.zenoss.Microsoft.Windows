##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version

THRESHOLDS = [
    'Low Available Memory',
    'CPU Utilization Critical',
    'CPU Utilization Warning',
    'Memory Paging Critical',
    'Memory Paging Warning',
    'Memory Usage Critical',
    'Memory Usage Warning',
    'Paging File Usage Critical',
    'Paging File Usage Warning',
    ]

class MigrateThresholds(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 4, 5)

    def migrate(self, dmd):
        # Remove unnecessary objects that were inadvertently added.
        organizer = dmd.Devices.getOrganizer('/Server/Microsoft')
        if organizer:
            for t in organizer.getRRDTemplates():
                if t.id == 'Device':
                    t.manage_deleteRRDThresholds(THRESHOLDS)
