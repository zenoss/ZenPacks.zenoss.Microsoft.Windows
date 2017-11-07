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


class RemoveMSExchangeTemplates(ZenPackMigration):
    version = Version(2, 8, 2)

    def migrate(self, dmd):
        for org in dmd.Devices.Server.Microsoft.getSubOrganizers():
            if set(('MSExchange2010IS', 'MSExchange2013IS')).issubset(org.zDeviceTemplates):
                org.zDeviceTemplates.remove('MSExchange2013IS')
                org.setZenProperty('zDeviceTemplates', org.zDeviceTemplates)
