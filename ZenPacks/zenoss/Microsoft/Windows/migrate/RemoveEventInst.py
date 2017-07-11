##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version
from Products.Zuul.interfaces import ICatalogTool
from Products.AdvancedQuery import Eq, Or
from Products.ZenEvents.EventClassInst import EventClassInst

log = logging.getLogger('zen.Microsoft.Windows.migrate.RemoveEventInst')


class RemoveEventInst(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 7, 9)

    def migrate(self, dmd):
        org = dmd.Events.getOrganizer('/Status/Kerberos')
        query = Or(Eq('id', 'KerberosAuthenticationFailure'), Eq('id', 'KerberosAuthenticationSuccess'))
        res = ICatalogTool(org).search(EventClassInst, query=query)
        if res.total:
            log.info('Removing unnecessary Event Class Instances')
            org.removeInstances(['KerberosAuthenticationFailure', 'KerberosAuthenticationSuccess'])
