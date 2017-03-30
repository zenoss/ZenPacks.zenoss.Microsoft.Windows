##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Zenpack's jobs.
"""

from ZODB.transact import transact
from transaction import commit
from zope.event import notify
from Products.Jobber.jobs import Job
from Products.Zuul.catalog.events import IndexingEvent
from Products.Zuul.interfaces import ICatalogTool
from Products.ZenUtils.events import pausedAndOptimizedIndexing

# ZenPack Imports
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
        org = self.dmd.Devices.getOrganizer('/Server/Microsoft')
        self.log.info('Searching for and removing incompatible winrmservices from devices.')
        devices_cleaned = 0
        for device in org.getSubDevicesGen():
            finished = False
            devices_cleaned += 1
            # This could take several passes
            while not finished:
                self.remove_winrmservices(device)
                finished = False if device.componentSearch(meta_type='WinRMService') else True
            if not devices_cleaned % 25:
                self.log.info('Committing devices with unclean winrmservices removed.')
                commit()
        commit()

        results = ICatalogTool(org).search(types=[
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

        self.log.info('Searching for components which need to be updated.')
        for result in results:
            if self.migrate_result(result):
                objects_migrated += 1
            if not objects_migrated % 1000:
                self.log.info('Committing 1000 objects with class types reset.')
                commit()
        # commit the last bit of objects
        self.log.info('Migrated {} components for use with ZenPacks.zenoss.ZenPackLib.'.format(objects_migrated))
        commit()

    @transact
    def remove_winrmservices(self, device):
        """Remove any stubborn WinRMServices"""
        for component in device.componentSearch(meta_type='WinRMService'):
            device.componentSearch.uncatalog_object(component.getPath())

    @transact
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
