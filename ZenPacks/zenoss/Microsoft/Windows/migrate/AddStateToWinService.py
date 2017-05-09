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

log = logging.getLogger('zen.Microsoft.Windows.migrate.AddStateToWinService')


class AddStateToWinService(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 7, 1)

    def add_state_ds_dp(self, template):
        if 'state' not in [ds.id for ds in template.datasources()]:
            ds = template.manage_addRRDDataSource('state', 'BuiltInDS.Built-In')
            ds.component = '${here/id}'
            ds.manage_addRRDDataPoint('state')

    def migrate(self, dmd):
        # Add state datasource/datapoint to subclasses
        # This will catch any device specific templates and make this migration quicker
        results = ICatalogTool(dmd.Devices.Server.Microsoft).search(RRDTemplate)
        if results.total == 0:
            return
        log.info('Searching for WinService templates.')
        templates = []
        for result in results:
            try:
                template = result.getObject()
            except Exception:
                continue
            if getattr(template, 'targetPythonClass', '') == 'ZenPacks.zenoss.Microsoft.Windows.WinService':
                templates.append(template)

        progress = progresslog.ProgressLogger(
            log,
            prefix="WinService state",
            total=results.total,
            interval=PROGRESS_LOG_INTERVAL)

        for template in templates:
            progress.increment()
            self.add_state_ds_dp(template)
