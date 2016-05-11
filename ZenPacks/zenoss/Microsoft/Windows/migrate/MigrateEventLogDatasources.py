##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
log = logging.getLogger("zen.migrate")

from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version

class MigrateEventLogDatasources(ZenPackMigration):
    ''' ensure datasource query is string and not list
        ZEN-23156
    '''
    version = Version(2, 5, 6)

    def migrate(self, dmd):
        '''
        This is the main method. It removes the 'IIS - Request Rate graph def.
        '''
        for t in dmd.Devices.getAllRRDTemplates():
            for ds in t.datasources():
                if ds.sourcetype == 'Windows EventLog':
                    if isinstance(ds.query, list):
                        ds.query = ' '.join(ds.query)

