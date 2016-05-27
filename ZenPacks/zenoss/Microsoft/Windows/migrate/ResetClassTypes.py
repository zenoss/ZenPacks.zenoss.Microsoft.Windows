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

LOG = logging.getLogger('zen.MicrosoftWindows')


class ResetClassTypes(ZenPackMigration):
    version = Version(2, 6, 0)

    def migrate(self, pack):
        catalog = ICatalogTool(pack.getDmdRoot('Devices'))

        klasses = [schema.CPU, schema.ClusterDisk, schema.ClusterInterface, 
                   schema.ClusterNetwork, schema.ClusterNode, schema.ClusterResource, 
                   schema.ClusterService, schema.FileSystem, schema.Interface, 
                   schema.OSProcess, schema.TeamInterface, schema.WinIIS, 
                   schema.WinSQLBackup, schema.WinSQLDatabase, schema.WinSQLInstance,
                   schema.WinSQLJob, schema.WinService]
        for klass in klasses:
            self.reset_class(catalog, klass)

    def reset_class(self, catalog, klass):
        '''reset portal_type and meta_type to class name'''
        name = klass.__name__
        results = catalog.search(klass)
        if not results.total:
            return

        LOG.info("Indexing %s %s objects", (results.total, name))
        for result in results:
            try:
                ob = result.getObject()
                ob.meta_type = name 
                ob.portal_type = name
            except Exception as e:
                continue

            ob.index_object()
            notify(IndexingEvent(ob))
