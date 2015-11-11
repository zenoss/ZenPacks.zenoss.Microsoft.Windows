##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version


class RemoveBadClusterDS(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 5, 0)

    def replaceDataSource(self, template, strategy, resource):
        template.manage_deleteRRDDataSources(['state', ])
        newds = template.manage_addRRDDataSource('state', 'ShellDataSource.ShellDataSource')
        newds.resource = resource
        newds.strategy = strategy
        newds.manage_addRRDDataPoint('state')

    def migrate(self, dmd):
        # Remove unnecessary objects that were inadvertently added.
        organizer = dmd.Devices.getOrganizer('/Server/Microsoft/Cluster')
        if organizer:
            for template in organizer.getRRDTemplates():
                if 'ClusterResource' == template.id:
                    self.replaceDataSource(template, 'powershell Cluster Resources', 'get-clusterresource')
                elif 'ClusterService' == template.id:
                    self.replaceDataSource(template, 'powershell Cluster Services', 'get-clustergroup')
