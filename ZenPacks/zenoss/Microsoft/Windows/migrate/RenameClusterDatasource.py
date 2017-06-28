##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version
from Products.Zuul.interfaces import ICatalogTool
from Products.ZenModel.RRDTemplate import RRDTemplate
from ZenPacks.zenoss.Microsoft.Windows import progresslog
PROGRESS_LOG_INTERVAL = 10

log = logging.getLogger('zen.Microsoft.Windows.migrate.RenameClusterDatasource')


class RenameClusterDatasource(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 7, 8)

    def migrate(self, dmd):
        # Add state datasource/datapoint to subclasses
        # This will catch any device specific templates and make this migration quicker
        results = ICatalogTool(dmd.Devices.Server.Microsoft).search(RRDTemplate)
        if results.total == 0:
            return
        log.info('Searching for Cluster templates to update.')
        templates = []
        cluster_templates = (
            'Cluster',
            'ClusterNode',
            'ClusterDisk',
            'ClusterNetwork',
            'ClusterResource',
            'ClusterInterface',
            'ClusterService')
        for result in results:
            try:
                template = result.getObject()
            except Exception:
                continue
            if template.id in cluster_templates:
                templates.append(template)

        progress = progresslog.ProgressLogger(
            log,
            prefix="Cluster template",
            total=len(templates),
            interval=PROGRESS_LOG_INTERVAL)

        for template in templates:
            progress.increment()
            for ds in template.datasources():
                if ds.sourcetype == 'Windows Shell' and 'powershell Cluster' in ds.strategy:
                    # 2.7.0 introduced unnecessary template/ds, just remove it
                    if template.id == 'Cluster':
                        template.manage_deleteRRDDataSources(['state', ])
                    else:
                        self.replaceDataSource(template, ds)
            # if the Cluster template is empty then remove it
            if template.id == 'Cluster' and len(template.datasources()) == 0:
                template.deviceClass().manage_deleteRRDTemplates((template.id,))

    def replaceDataSource(self, template, ds):
        cycletime = ds.cycletime
        severity = ds.severity
        eventClass = ds.eventClass
        eventKey = ds.eventKey
        enabled = ds.enabled
        try:
            description = ds.datapoints()[0].description
        except Exception:
            pass
        if 'description' not in locals() or len(description) == 0:
            description = 'Used to monitor the state of the Cluster Nodes.'
        template.manage_deleteRRDDataSources(['state', ])
        newds = template.manage_addRRDDataSource('state', 'ClusterDataSource.ClusterDataSource')
        newds.sourcetype = 'Windows Cluster'
        newds.cycletime = cycletime
        newds.severity = severity
        newds.eventClass = eventClass
        newds.eventKey = eventKey
        newds.enabled = enabled
        dp = newds.manage_addRRDDataPoint('state')
        dp.description = description
