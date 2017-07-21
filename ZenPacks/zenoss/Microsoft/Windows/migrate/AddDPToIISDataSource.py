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
from ZenPacks.zenoss.Microsoft.Windows import progresslog
from ZenPacks.zenoss.Microsoft.Windows.datasources.IISSiteDataSource import IISSiteDataSource
PROGRESS_LOG_INTERVAL = 10

log = logging.getLogger('zen.Microsoft.Windows.migrate.AddDPToIISDataSource')


class AddDPToIISDataSource(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 7, 9)

    def add_status_dp(self, datasource):
        if not datasource:
            return
        if 'status' not in [dp.id for dp in datasource.datapoints()]:
            datasource.manage_addRRDDataPoint('status')

    def migrate(self, dmd):
        # Add state datasource/datapoint to subclasses
        # This will catch any device specific templates and make this migration quicker
        log.info('Searching for IISSiteDataSources.')
        results = ICatalogTool(dmd.Devices.Server.Microsoft).search(IISSiteDataSource)
        if results.total == 0:
            return
        progress = progresslog.ProgressLogger(
            log,
            prefix="IISSiteSiteDataSource",
            total=results.total,
            interval=PROGRESS_LOG_INTERVAL)
        for result in results:
            try:
                datasource = result.getObject()
            except Exception:
                continue
            progress.increment()
            self.add_status_dp(datasource)
