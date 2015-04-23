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

class MigrateMSExchangeIS(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 4, 1)

    def migrate(self, dmd):
        # This is the main method. It removes the 'MSExchangeIS' monitoring template.
        # MSExchangeIS is also the name of a winrmservice so do not remove if a user
        # has created it.  Also change msexchangeversion so we know how to find
        # the correct monitoring template
        organizer = dmd.Devices.getOrganizer('/Server/Microsoft')
        if organizer:
            ok_to_remove = True
            for template in organizer.getRRDTemplates():
                if 'MSExchangeIS' in template.id:
                    if 'DefaultService' in [ds.id for ds in template.getRRDDataSources()]:
                        ok_to_remove = False
                        break
            if ok_to_remove:
                organizer.manage_deleteRRDTemplates(['MSExchangeIS'])
            try:
                for device in organizer.devices():
                    if device.msexchangeversion == 'MSExchangeIS':
                        device.msexchangeversion = 'MSExchangeInformationStore'
            except:
                pass