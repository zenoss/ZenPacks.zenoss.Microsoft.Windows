##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version


class AddStateToWinService(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 7, 1)

    def add_to_organizer(self, organizer):
        for t in organizer.getRRDTemplates():
            if getattr(t, 'targetPythonClass', '') == 'ZenPacks.zenoss.Microsoft.Windows.WinService':
                dc = t.deviceClass()
                if dc is None:
                    dc = t.getPrimaryParent()
                # skip inherited templates
                if dc.getPrimaryUrlPath() == organizer.getPrimaryUrlPath():
                    if 'state' not in [ds.id for ds in t.datasources()]:
                        ds = t.manage_addRRDDataSource('state', 'BuiltInDS.Built-In')
                        ds.component = '${here/id}'
                        ds.manage_addRRDDataPoint('state')

    def migrate(self, dmd):
        # Add state datasource/datapoint to subclasses
        organizer = dmd.Devices.getOrganizer('/Server/Microsoft')
        if organizer:
            for suborg in organizer.getSubOrganizers():
                self.add_to_organizer(suborg)
