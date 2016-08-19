##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
LOG = logging.getLogger("zen.Microsoft.Windows.migrate.{}".format(__name__))

# Zenoss Imports
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.Zuul.interfaces import ICatalogTool

# ZenPack Imports
from ZenPacks.zenoss.Microsoft.Windows import progresslog
from ZenPacks.zenoss.Microsoft.Windows.Device import Device
from ZenPacks.zenoss.Microsoft.Windows.OperatingSystem import OperatingSystem


# If the migration takes longer than this interval, a running progress
# showing elapsed and estimated remaining time will be logged this
# often. The value is in seconds.
PROGRESS_LOG_INTERVAL = 10


class AddOSRelations(ZenPackMigration):

    version = Version(2, 6, 3)

    def migrate(self, pack):
        results = ICatalogTool(pack.dmd.Devices).search(Device)

        LOG.info("starting: %s total devices", results.total)
        progress = progresslog.ProgressLogger(
            LOG,
            prefix="progress",
            total=results.total,
            interval=PROGRESS_LOG_INTERVAL)

        objects_migrated = 0

        for result in results:
            try:
                if self.updateRelations(result.getObject()):
                    objects_migrated += 1
            except Exception:
                LOG.exception(
                    "error updating relationships for %s", result.id)

            progress.increment()

        LOG.info(
            "finished: %s of %s devices required migration",
            objects_migrated,
            results.total)

    def updateRelations(self, device):
        for relname in (x[0] for x in OperatingSystem._relations):
            if not device.os.aqBaseHasAttr(relname):
                device.os.buildRelations()
                return True

        return False
