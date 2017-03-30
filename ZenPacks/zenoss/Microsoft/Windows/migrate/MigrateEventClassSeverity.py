##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenRelations.ZenPropertyManager import ZenPropertyDoesNotExist


class MigrateEventClassSeverity(ZenPackMigration):
    """Fixes ZEN-26632

    Windows Event Log events come across as Info Events
    """
    version = Version(2, 7, 0)

    def migrate(self, dmd):
        try:
            organizer = dmd.Events.getOrganizer('/Win/evtsys')
        except KeyError:
            organizer = None
        if organizer:
            try:
                organizer.deleteZenProperty('zEventSeverity')
            except ZenPropertyDoesNotExist:
                pass
