##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""Reindex Windows services.

ZEN-21603
services need to be reindexed to update stale datasources.

"""

# Logging
import logging

# Zenoss Imports
from zope.event import notify
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.Zuul.catalog.events import IndexingEvent
from Products.Zuul.interfaces import ICatalogTool

# ZenPack Imports
from ZenPacks.zenoss.Microsoft.Windows.WinService import WinService

LOG = logging.getLogger('zen.MicrosoftWindows')


class ReindexWinService(ZenPackMigration):
    version = Version(2, 5, 6)

    def migrate(self, pack):
        catalog = ICatalogTool(pack.getDmdRoot('Devices'))
        results = catalog.search(WinService)

        if not results.total:
            return

        LOG.info(
            "Indexing %s Windows Services.",
            results.total)

        for result in results:
            try:
                epg = result.getObject()
            except Exception:
                continue

            epg.index_object()
            notify(IndexingEvent(epg))
