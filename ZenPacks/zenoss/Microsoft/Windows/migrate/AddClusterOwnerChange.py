##############################################################################
#
# Copyright (C) Zenoss, Inc. 2019, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version

log = logging.getLogger('zen.Microsoft.Windows')


class AddClusterOwnerChange(ZenPackMigration):
    """Main class that contains the migrate() method.

    Note version setting.
    """

    version = Version(2, 9, 3)

    def get_objects(self, dmd):
        """Get objects to migrate."""
        for ob in [dmd.Devices.Server.Microsoft.Cluster] +\
                dmd.Devices.Server.Microsoft.Cluster.getSubOrganizers() +\
                dmd.Devices.Server.Microsoft.Cluster.getSubDevices():
            yield ob

    def migrate(self, dmd):
        """Run migration."""
        log.info('Ensuring event class key clusterOwnerChange '
                 'in zWindowsRemodelEventClassKeys')
        for ob in self.get_objects(dmd):
            self.update_zprop(ob)

    def update_zprop(self, thing):
        """Ensure clusterOwnerChange is in zWindowsRemodelEventClassKeys."""
        if not hasattr(thing, 'zWindowsRemodelEventClassKeys'):
            return

        if not thing.isLocal('zWindowsRemodelEventClassKeys') and not\
                thing.getPrimaryUrlPath() ==\
                '/zport/dmd/Devices/Server/Microsoft/Cluster':
            return

        zWindowsRemodelEventClassKeys = thing.zWindowsRemodelEventClassKeys
        if 'clusterOwnerChange' not in zWindowsRemodelEventClassKeys:
            zWindowsRemodelEventClassKeys.append('clusterOwnerChange')
            thing.setZenProperty(
                'zWindowsRemodelEventClassKeys',
                zWindowsRemodelEventClassKeys)
