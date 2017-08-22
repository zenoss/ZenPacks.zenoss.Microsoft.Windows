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
PROGRESS_LOG_INTERVAL = 10

log = logging.getLogger('zen.Microsoft.Windows.migrate.AddDPToWinDatabaseTemplate')


class AddDPToWinDatabaseTemplate(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 8, 0)

    def add_status_ds_dp(self, template):
        if 'status' not in [ds.id for ds in template.datasources()]:
            ds = template.manage_addRRDDataSource('status', 'ShellDataSource.Windows Shell')
            ds.component = '${here/id}'
            ds.resource = 'status'
            ds.strategy = 'powershell MSSQL'
            ds.eventClass = '/Status'
            ds.manage_addRRDDataPoint('status')

    def migrate(self, dmd):
        # Add state datasource/datapoint to subclasses
        # This will catch any device specific templates and make this migration quicker
        results = ICatalogTool(dmd.Devices.Server.Microsoft).search('Products.ZenModel.RRDTemplate.RRDTemplate')
        if results.total == 0:
            return
        log.info('Searching for WinService templates.')
        templates = []
        for result in results:
            try:
                template = result.getObject()
            except Exception:
                continue
            if getattr(template, 'targetPythonClass', '') == 'ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase':
                templates.append(template)

        progress = progresslog.ProgressLogger(
            log,
            prefix="WinService state",
            total=len(templates),
            interval=PROGRESS_LOG_INTERVAL)

        for template in templates:
            progress.increment()
            self.add_status_ds_dp(template)
