##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""Reset meta_type and portal_type for objects that need it."""

# Logging
import logging

# Zenoss Imports
from zope.event import notify
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.Zuul.catalog.events import IndexingEvent
from Products.Zuul.interfaces import ICatalogTool

# ZenPack Imports
from ZenPacks.zenoss.Microsoft.Windows import progresslog
LOG = logging.getLogger("zen.Microsoft.Windows.migrate.{}".format(__name__))


# If the migration takes longer than this interval, a running progress
# showing elapsed and estimated remaining time will be logged this
# often. The value is in seconds.
PROGRESS_LOG_INTERVAL = 10


class ResetOSProcesses(ZenPackMigration):
    version = Version(2, 7, 0)

    def migrate(self, pack):
        LOG.info("Reindexing Processes")
        results = ICatalogTool(pack.getDmdRoot("Devices")).search(types=(
            'ZenPacks.zenoss.Microsoft.Windows.OSProcess.OSProcess',
        ))

        if not results.total:
            return

        LOG.info("Found {} Processes that may require indexing".format(results.total))
        progress = progresslog.ProgressLogger(
            LOG,
            prefix="progress",
            total=results.total,
            interval=PROGRESS_LOG_INTERVAL)

        objects_migrated = 0

        for result in results:
            if self.migrate_result(result):
                objects_migrated += 1

            progress.increment()

        LOG.info(
            "Finished indexing {} of {} Processes".format(objects_migrated, results.total))

    def migrate_result(self, result):
        """Return True if result needed to be migrated.
        Reindex object
        """
        try:
            obj = result.getObject()
        except Exception:
            return False

        obj.index_object()
        notify(IndexingEvent(obj))

        return True
