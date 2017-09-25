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


class AddMSExchangeTemplates(ZenPackMigration):
    version = Version(2, 8, 1)

    def migrate(self, dmd):
        organizer = dmd.Devices.getOrganizer('/Server/Microsoft/Windows')
        if organizer:
            organizers = [organizer] + organizer.getSubOrganizers()

            for organizer in organizers:
                templates = organizer.zDeviceTemplates
                for t in ['MSExchange2010IS', 'MSExchange2013IS']:
                    if t not in templates:
                        templates.append(t)

                organizer.setZenProperty('zDeviceTemplates', templates)
