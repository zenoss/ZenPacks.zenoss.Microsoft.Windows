##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Zenpack's jobs.
"""

from zope.event import notify
from Products.Jobber.jobs import Job
from Products.Zuul.catalog.events import IndexingEvent
from Products.Zuul.interfaces import ICatalogTool
from Products.ZenUtils.events import pausedAndOptimizedIndexing

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
from ZenPacks.zenoss.Microsoft.Windows.WinService import WinService


class ReindexWinServices(Job):

    """Job for reindexing affected Windows services components when related
    datasource was updated.
    """

    @classmethod
    def getJobType(cls):
        return "Reindex Windows services"

    @classmethod
    def getJobDescription(cls, *args, **kwargs):
        return "Reindex Windows services linked to {uid} template".format(**kwargs)

    def _run(self, uid, **kwargs):
        template = self.dmd.unrestrictedTraverse(uid)

        for service in template.getAffectedServices():
            service.index_object()


class ResetClassTypes(Job):
    """Job for resetting class types when upgrading to 2.7.0.  Needed for changing
    to ZPL classes
    """
    @classmethod
    def getJobType(cls):
        return "Reset Microsoft Windows Class Types"

    @classmethod
    def getJobDescription(self, *args, **kwargs):
        return "Reset class types for upgrade to new ZenPackLib classes."

    def _run(self, **kwargs):
        results = ICatalogTool(self.dmd.getDmdRoot("Devices")).search(types=[
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
            WinService,
        ])

        if not results.total:
            return

        objects_migrated = 0

        for result in results:
            if self.migrate_result(result):
                objects_migrated += 1

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
            with pausedAndOptimizedIndexing(obj.index_object()):
                notify(IndexingEvent(obj))
                migrated = True

        return migrated
