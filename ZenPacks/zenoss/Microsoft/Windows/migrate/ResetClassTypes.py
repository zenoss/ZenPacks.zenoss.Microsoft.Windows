##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""

Reset meta_type and portal_types for objects

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
from ZenPacks.zenoss.Microsoft.Windows import schema
from ZenPacks.zenoss.Microsoft.Windows.WinService import WinService
from ZenPacks.zenoss.Microsoft.Windows.CPU import CPU
from ZenPacks.zenoss.Microsoft.Windows.ClusterDisk import ClusterDisk
from ZenPacks.zenoss.Microsoft.Windows.ClusterInterface import ClusterInterface
from ZenPacks.zenoss.Microsoft.Windows.ClusterNetwork import ClusterNetwork
from ZenPacks.zenoss.Microsoft.Windows.ClusterNode import ClusterNode
from ZenPacks.zenoss.Microsoft.Windows.ClusterResource import ClusterResource
from ZenPacks.zenoss.Microsoft.Windows.ClusterService import ClusterService
from ZenPacks.zenoss.Microsoft.Windows.FileSystem import FileSystem
from ZenPacks.zenoss.Microsoft.Windows.Interface import Interface
from ZenPacks.zenoss.Microsoft.Windows.OSProcess import OSProcess
from ZenPacks.zenoss.Microsoft.Windows.TeamInterface import TeamInterface
from ZenPacks.zenoss.Microsoft.Windows.WinIIS import WinIIS
from ZenPacks.zenoss.Microsoft.Windows.WinSQLBackup import WinSQLBackup
from ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase import WinSQLDatabase
from ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance import WinSQLInstance
from ZenPacks.zenoss.Microsoft.Windows.WinSQLJob import WinSQLJob

LOG = logging.getLogger('zen.MicrosoftWindows')


class ResetClassTypes(ZenPackMigration):
    version = Version(2, 6, 0)

    def migrate(self, pack):
        LOG.info('Resetting component attributes')
        catalog = ICatalogTool(pack.getDmdRoot('Devices'))

        klasses = [CPU, ClusterDisk, ClusterInterface, 
                   ClusterNetwork, ClusterNode, ClusterResource, 
                   ClusterService, FileSystem, Interface, 
                   OSProcess, TeamInterface, WinIIS, 
                   WinSQLBackup, WinSQLDatabase, WinSQLInstance,
                   WinSQLJob]
        for klass in klasses:
            self.reset_class(catalog, klass)

    def reset_class(self, catalog, klass):
        '''reset portal_type and meta_type to class name'''
        name = klass.__name__
        results = catalog.search(klass)
        if not results.total:
            return

        LOG.info("Indexing %s %s objects" % (results.total, name))
        for result in results:
            try:
                ob = result.getObject()
                ob.meta_type = name 
                ob.portal_type = name
            except Exception as e:
                log.warn('problem setting to "%s"' % (name))
                continue

            ob.index_object()
            notify(IndexingEvent(ob))
