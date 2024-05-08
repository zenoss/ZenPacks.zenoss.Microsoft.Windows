##############################################################################
#
# Copyright (C) Zenoss, Inc. 2024, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version

log = logging.getLogger("zen.migrate")


class RemoveSoftwareModelerPluginFromDefaults(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(3, 1, 1)

    def get_objects(self, dmd):
        objects = []
        dcObject = dmd.Devices.getOrganizer('/Server/Microsoft/Windows')
        objects.append(dcObject)
        objects.extend(dcObject.getOverriddenObjects("zCollectorPlugins", showDevices=True))
        for ob in objects:
            yield ob

    def migrate(self, pack):
        try:
            for ob in self.get_objects(pack.dmd):
                zCollectorPlugins = getattr(ob, "zCollectorPlugins", [])
                if 'zenoss.winrm.Software' in zCollectorPlugins:
                    zCollectorPlugins.remove('zenoss.winrm.Software')
                    ob.setZenProperty('zCollectorPlugins', zCollectorPlugins)
            log.info("Successfully removed 'zenoss.winrm.Software' modeler plugin from the defaults.")
        except Exception as e:
            log.warning("Failed to remove 'zenoss.winrm.Software' modeler plugin with a message - {}".format(e))
