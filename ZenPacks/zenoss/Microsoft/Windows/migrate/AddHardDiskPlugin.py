##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""Add HardDisks plugin

ZPL 2.0 does not overwrite existing zProperties for a device class
"""
# logging
import logging

# Zenoss Imports
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration

log = logging.getLogger('zen.Microsoft.Windows')


class AddHardDiskPlugin(ZenPackMigration):
    version = Version(2, 7, 0)

    def migrate(self, pack):
        dcObject = pack.dmd.Devices.getOrganizer('/Server/Microsoft/Windows')
        zCollectorPlugins = dcObject.zCollectorPlugins
        if 'zenoss.winrm.HardDisks' not in zCollectorPlugins:
            log.debug('Adding HardDisks modler plugin to zCollectorPlugins for'
                      ' /Server/Microsoft/Windows')
            zCollectorPlugins.append('zenoss.winrm.HardDisks')
            dcObject.setZenProperty('zCollectorPlugins', zCollectorPlugins)
