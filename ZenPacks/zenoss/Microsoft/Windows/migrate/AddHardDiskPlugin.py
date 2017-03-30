##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
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
        new_plugin = 'zenoss.winrm.HardDisks'
        ref_plugin = 'zenoss.winrm.FileSystems'

        dcObject = pack.dmd.Devices.getOrganizer('/Server/Microsoft/Windows')
        zCollectorPlugins = dcObject.zCollectorPlugins
        if new_plugin not in zCollectorPlugins:
            log.debug('Adding HardDisks modeler plugin to zCollectorPlugins for'
                      ' /Server/Microsoft/Windows')
            zCollectorPlugins.append(new_plugin)
            dcObject.setZenProperty('zCollectorPlugins', zCollectorPlugins)

        # apply also to any sub-device classes or devices with locally defined plugins
        for ob in dcObject.getOverriddenObjects("zCollectorPlugins", showDevices=True):
            collector_plugins = ob.zCollectorPlugins
            # skip if object doesn't use the FileSystems plugin
            if ref_plugin not in collector_plugins:
                continue
            if new_plugin not in collector_plugins:
                log.debug('Adding HardDisks modeler plugin to zCollectorPlugins for {}'.format(ob.getDmdKey()))
                collector_plugins.append(new_plugin)
                ob.setZenProperty('zCollectorPlugins', collector_plugins)
