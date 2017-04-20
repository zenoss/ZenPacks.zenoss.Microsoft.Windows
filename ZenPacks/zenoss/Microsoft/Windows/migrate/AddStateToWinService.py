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

    def add_to_organizer(self, organizer):
        for t in organizer.getRRDTemplates():
            if getattr(t, 'targetPythonClass', '') == 'ZenPacks.zenoss.Microsoft.Windows.WinService':
                dc = t.deviceClass()
                if dc is None:
                    dc = t.getPrimaryParent()
                # skip inherited templates
                if dc.getPrimaryUrlPath() == organizer.getPrimaryUrlPath():
                    self.add_state_ds_dp(t)

    def migrate(self, dmd):
        # Add state datasource/datapoint to subclasses
        log.info('Updating WinService templates on subclasses and devices.')
        organizer = dmd.Devices.getOrganizer('/Server/Microsoft')
        if organizer:
            for suborg in organizer.getSubOrganizers():
                self.add_to_organizer(suborg)

        # Add state ds/dp to any local device templates
        results = ICatalogTool(dmd.getDmdRoot("Devices")).search(types=(
            'ZenPacks.zenoss.Microsoft.Windows.BaseDevice.BaseDevice',
        ))

        if not results.total:
            return

        for r in results:
            try:
                dev = r.getObject()
            except Exception:
                continue
            if hasattr(dev.os, 'winservices'):
                for service in dev.os.winservices():
                    for template in service.getRRDTemplates():
                        template_path = template.getRRDPath()
                        if template_path.find(dev.id) >= 0:
                            self.add_state_ds_dp(template)
