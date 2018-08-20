##############################################################################
#
# Copyright (C) Zenoss, Inc. 2018, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version

log = logging.getLogger('zen.Microsoft.Windows')


class RemoveExtraClusterPlugins(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 9, 1)

    def get_objects(self, dmd):
        for ob in dmd.Devices.Server.Microsoft.Cluster.getSubOrganizers() +\
                dmd.Devices.Server.Microsoft.Cluster.getSubDevices():
            yield ob

    def migrate(self, dmd):
        for ob in self.get_objects(dmd):
            self.remove_extra(ob)

    def remove_extra(self, thing):
        """Removes extra occurrences of WinCluster in zCollectorPlugins"""

        if not hasattr(thing, 'zCollectorPlugins'):
            return

        if not thing.isLocal('zCollectorPlugins'):
            return

        zCollectorPlugins = thing.zCollectorPlugins
        if zCollectorPlugins.count('zenoss.winrm.WinCluster') > 1:
            thing.setZenProperty('zCollectorPlugins', list(set(zCollectorPlugins)))
