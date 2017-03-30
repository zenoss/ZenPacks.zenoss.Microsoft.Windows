##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import json
import logging

from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration
log = logging.getLogger("zen.migrate")


class MigrateDBInstances(ZenPackMigration):
    ''' Main class that contains the migrate() method.
    Note version setting. '''
    version = Version(2, 7, 0)

    def get_objects(self, pack):
        for ob in pack.dmd.Devices.getSubOrganizers() + pack.dmd.Devices.getSubDevices():
            yield ob

    def migrate(self, pack):
        '''
        This is the main method. Its migrates the data to the new format of
        properties.
        '''
        for ob in self.get_objects(pack):
            self.migrate_sql_settings(ob)

    def migrate_sql_settings(self, thing):
        ''' Converts zDBInstances and zDBInstancesPassword to new format '''

        if not hasattr(thing, 'zDBInstances'):
            return

        if not thing.isLocal('zDBInstances'):
            return

        try:
            # Successful load mean we already have proper value
            if not isinstance(json.loads(thing.zDBInstances), list):
                raise
        except Exception:
            log.info("Migrating zDBInstances for %s", thing.getDmdKey())

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
