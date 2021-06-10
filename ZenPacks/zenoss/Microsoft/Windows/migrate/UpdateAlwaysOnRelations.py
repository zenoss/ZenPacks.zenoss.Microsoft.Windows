##############################################################################
#
# Copyright (C) Zenoss, Inc. 2021, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.Zuul.interfaces import ICatalogTool
from ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance import WinSQLInstance
from ZenPacks.zenoss.Microsoft.Windows.OperatingSystem import OperatingSystem
from ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase import WinSQLDatabase

import logging
log = logging.getLogger("zen.migrate")


class UpdateAlwaysOnRelations(ZenPackMigration):
    """
    Update relations for Always On component.
    """
    version = Version(3, 0, 0)

    def migrate(self, pack):
        log.debug(
            "Update Always On relations"
        )

        catalog = ICatalogTool(pack.dmd.Devices)

        for brain in catalog.search(types=[OperatingSystem, WinSQLInstance, WinSQLDatabase]):
            try:
                brain.getObject().buildRelations()
            except Exception:
                pass
