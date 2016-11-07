##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version
from Products.Zuul.interfaces import ICatalogTool
from ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance import WinSQLInstance


class MigrateSQLInstances(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 6, 6)

    def migrate(self, dmd):
        results = ICatalogTool(dmd.getDmdRoot("Devices")).search(types=[WinSQLInstance])
        for result in results:
            try:
                obj = result.getObject()
            except Exception:
                continue

            version = getattr(obj, 'sql_server_version', None)
            if version == 'None' or version is None:
                obj.sql_server_version = 'Unknown'
