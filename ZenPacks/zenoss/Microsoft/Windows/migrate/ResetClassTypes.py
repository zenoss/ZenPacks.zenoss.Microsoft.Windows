##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""Reset meta_type and portal_type for objects that need it."""

# Logging
import logging
LOG = logging.getLogger("zen.Microsoft.Windows.migrate.{}".format(__name__))

# Zenoss Imports
from zope.event import notify
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.Zuul.catalog.events import IndexingEvent
from Products.Zuul.interfaces import ICatalogTool

# ZenPack Imports
from ZenPacks.zenoss.Microsoft.Windows import progresslog
from ZenPacks.zenoss.Microsoft.Windows.ClusterDisk import ClusterDisk
from ZenPacks.zenoss.Microsoft.Windows.ClusterInterface import ClusterInterface
from ZenPacks.zenoss.Microsoft.Windows.ClusterNetwork import ClusterNetwork
from ZenPacks.zenoss.Microsoft.Windows.ClusterNode import ClusterNode
from ZenPacks.zenoss.Microsoft.Windows.ClusterResource import ClusterResource
from ZenPacks.zenoss.Microsoft.Windows.ClusterService import ClusterService
from ZenPacks.zenoss.Microsoft.Windows.CPU import CPU
from ZenPacks.zenoss.Microsoft.Windows.FileSystem import FileSystem
from ZenPacks.zenoss.Microsoft.Windows.Interface import Interface
from ZenPacks.zenoss.Microsoft.Windows.OSProcess import OSProcess
from ZenPacks.zenoss.Microsoft.Windows.TeamInterface import TeamInterface
from ZenPacks.zenoss.Microsoft.Windows.WinIIS import WinIIS
from ZenPacks.zenoss.Microsoft.Windows.WinSQLBackup import WinSQLBackup
from ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase import WinSQLDatabase
from ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance import WinSQLInstance
from ZenPacks.zenoss.Microsoft.Windows.WinSQLJob import WinSQLJob


# If the migration takes longer than this interval, a running progress
# showing elapsed and estimated remaining time will be logged this
# often. The value is in seconds.
PROGRESS_LOG_INTERVAL = 10


class ResetClassTypes(ZenPackMigration):
    version = Version(2, 6, 3)

    def migrate(self, pack):
        LOG.info("searching for objects")
        results = ICatalogTool(pack.getDmdRoot("Devices")).search(types=[
            ClusterDisk,
            ClusterInterface,
            ClusterNetwork,
            ClusterNode,
            ClusterResource,
            ClusterService,
            CPU,
            FileSystem,
            Interface,
            OSProcess,
            TeamInterface,
            WinIIS,
            WinSQLBackup,
            WinSQLDatabase,
            WinSQLInstance,
            WinSQLJob,
            ])

        if not results.total:
            LOG.info("no objects to migrate")
            return

        LOG.info("starting: %s total objects", results.total)
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
            "finished: %s of %s objects required migration",
            objects_migrated,
            results.total)

    def migrate_result(self, result):
        """Return True if result needed to be migrated.

        Delete instance properties that shadow class properties, and reindex
        the object if its resulting meta_type no longer matches its indexed
        meta_type.

        """
        try:
            obj = result.getObject()
        except Exception:
            return False

        migrated = False

        try:
            del(obj.meta_type)
        except Exception:
            pass
        else:
            migrated = True

        try:
            del(obj.portal_type)
        except Exception:
            pass
        else:
            migrated = True

        if result.meta_type != obj.meta_type:
            obj.index_object()
            notify(IndexingEvent(obj))
            migrated = True

        return migrated
