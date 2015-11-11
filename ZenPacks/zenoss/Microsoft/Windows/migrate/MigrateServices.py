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
from ZenPacks.zenoss.Microsoft.Windows.datasources.ServiceDataSource import ServiceDataSource

class MigrateServices(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 4, 6)

    def migrate(self, dmd):
        organizer = dmd.Devices.getOrganizer('/Server/Microsoft')
        if organizer:
            for template in organizer.getRRDTemplates():
                for ds in template.getRRDDataSources():
                    if isinstance(ds, ServiceDataSource):
                        if ds.startmode == 'Any':
                            ds.startmode = 'Auto,Manual,Disabled'
