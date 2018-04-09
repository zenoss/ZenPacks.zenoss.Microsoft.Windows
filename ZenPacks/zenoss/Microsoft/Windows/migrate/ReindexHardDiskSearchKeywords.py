##############################################################################
#
# Copyright (C) Zenoss, Inc. 2018, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging

from zope.event import notify
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version
from Products.Zuul.interfaces import ICatalogTool
from Products.Zuul.catalog.events import IndexingEvent

from ZenPacks.zenoss.Microsoft.Windows.HardDisk import HardDisk

log = logging.getLogger("zen.migrate")

__doc__ = """
Reindex HardDisk components to add keyword search indexes and update IndexableWrapper
"""


class ReindexHardDiskSearchKeywords(ZenPackMigration):
    """
    Update searchKeywords index for existing HardDisk components
    """
    version = Version(2, 9, 1)

    def migrate(self, pack):
        hd_fs_brains = ICatalogTool(pack.dmd.Devices).search(HardDisk)
        for result in hd_fs_brains:
            try:
                notify(IndexingEvent(result.getObject()))
            except Exception:
                continue
