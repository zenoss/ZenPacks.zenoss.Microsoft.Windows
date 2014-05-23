##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import json
import logging
log = logging.getLogger("zen.migrate")


from Products.ZenModel.DeviceClass import DeviceClass
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration


DEVICE_CLASSES = [
    '/Server/Microsoft/Windows/SQL',
    '/Server/Microsoft/Windows',
    '/Server/Microsoft/Cluster',
    '/'
]


def name_for_thing(widget):
    ''' Helper function to provide the name of the Device or DeviceClass '''

    if isinstance(widget, DeviceClass):
        return widget.getOrganizerName()

    return widget.titleOrId()


class MigrateDBInstances(ZenPackMigration):
    ''' Main class that contains the migrate() method.
    Note version setting. '''
    version = Version(2, 1, 0)

    def migrate(self, dmd):
        '''
        This is the main method. Its migrates the data to the new format of
        properties.
        '''
        for dc in DEVICE_CLASSES:
            organizer = self.get_organizer(dc, dmd)
            if organizer:
                for device in organizer.devices():
                    self.migrate_sql_settings(device)

        for dc in DEVICE_CLASSES:
            organizer = self.get_organizer(dc, dmd)
            if organizer:
                self.migrate_sql_settings(organizer)

    def get_organizer(self, dc, dmd):
        try:
            return dmd.Devices.getOrganizer(dc)
        except Exception as e:
            return None

    def migrate_sql_settings(self, thing):
        ''' Converts zDBInstances and zDBInstancesPassword to new format '''

        if not thing.zDBInstances:
            return

        try:
            # Successful load mean we already have proper value
            if not isinstance(json.loads(thing.zDBInstances), list):
                raise
        except:
            log.info("Migrating zDBInstances for %s", name_for_thing(thing))

            res = []
            if isinstance(thing.zDBInstances, list):
                res = thing.zDBInstances
                res[0]['instance'] = "MSSQLSERVER"
            else:
                instances = thing.zDBInstances.split(';')
                credentials = []
                if thing.hasProperty('zDBInstancesPassword'):
                    credentials = thing.zDBInstancesPassword.split(';')
                # a) no passwords, only MSSQL instances
                if not credentials:
                    for instance in instances:
                        if instance:
                            res.append({
                                "instance": instance,
                                "user": "",
                                "passwd": ""
                            })
                # b) passwords in zDBInstancesPassword
                else:
                    for instance, cred in zip(instances, credentials):
                        if instance:
                            user, passwd = '', ''
                            if cred:
                                user, passwd = cred.split(':')
                            res.append({
                                "instance": instance,
                                "user": user,
                                "passwd": passwd
                            })
            # print json.dumps(res)
            thing.setZenProperty('zDBInstances', json.dumps(res))


MigrateDBInstances()
