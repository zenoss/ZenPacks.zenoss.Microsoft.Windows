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

class RemoveObjects(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 4, 3)

    def migrate(self, dmd):
        # Remove unnecessary objects that were inadvertently added.
        organizer = dmd.Devices.getOrganizer('/Server/Microsoft')
        if organizer:
            organizer.manage_deleteRRDTemplates(['ALG','AppInfo','Appinfo','BFE','EventLog', 'Ec2Config','copy_of_WinService','IISADMIN'])
        organizer = dmd.Devices.getOrganizer('/Server/Microsoft/Windows')
        if organizer:
            organizer.manage_deleteRRDTemplates(['ShellTests'])

        dmd.Devices.manage_deleteOrganizers(['/Server/Microsoft/Windows/solo','/Server/Microsoft/Windows/servicetest'])