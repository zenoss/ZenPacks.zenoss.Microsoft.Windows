##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""Remove Windows services.

ZEN-24347
winrmservices need to be removed as they are incompatible with the WinService
class.

"""

# Logging
import logging

# Zenoss Imports
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.Zuul.interfaces import ICatalogTool

LOG = logging.getLogger('zen.MicrosoftWindows')


class RemoveWinRMServices(ZenPackMigration):
    version = Version(2, 7, 1)

    def migrate(self, pack):

        results = ICatalogTool(pack.getDmdRoot("Devices")).search(types=(
            'ZenPacks.zenoss.Microsoft.Windows.BaseDevice.BaseDevice',
        ))

        if not results.total:
            return

        LOG.info('Removing incompatible Windows Services from %s devices', results.total)

        for r in results:
            try:
                device = r.getObject()
                device.os.removeRelation('winrmservices', suppress_events=True)
            except Exception:
                continue
