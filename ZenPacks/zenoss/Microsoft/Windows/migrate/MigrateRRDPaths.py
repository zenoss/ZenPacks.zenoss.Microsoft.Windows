##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""Remove Windows services.
ZPS-1204
Prevent data loss due to rrdPath changes between ZPL and non-ZPL-based versions
of this zenpack

"""

# Logging
import logging
import pkg_resources
# Zenoss Imports
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration

LOG = logging.getLogger('zen.MicrosoftWindows')


class MigrateRRDPaths(ZenPackMigration):
    version = Version(2, 7, 0)

    def migrate(self, pack):
        if pack.prevZenPackVersion is None:
            return
        installed_version = pkg_resources.parse_version(pack.prevZenPackVersion)
        # we only want to set this if upgrading directly from 2.5.x
        if installed_version < pkg_resources.parse_version('2.6.0'):
            LOG.info('Setting zWinUseLegacyRRDPath to True we are upgrading directly from 2.5.x')
            pack.dmd.Devices.setZenProperty('zWinUseLegacyRRDPath', True)
