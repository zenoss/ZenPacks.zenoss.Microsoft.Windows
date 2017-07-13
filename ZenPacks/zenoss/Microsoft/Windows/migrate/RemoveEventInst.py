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
BAD_PATHS = (
    '/Status/Kerberos/Auth',
    '/Status/Kerberos/Failure',
    '/Status/Winrm/Auth/PasswordExpired',
    '/Status/Winrm/Auth/WrongCredentials')
KRB_INSTANCES = (
    'KerberosAuthenticationFailure',
    'KerberosAuthenticationSuccess',
    'KerberosSuccess',
    'KerberosFailure',
    'Failure Default')
AUTH_INSTANCES = (
    'Wrong Credentials Default',
    'AuthenticationSuccess',
    'AuthenticationFailure')


class RemoveEventInst(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 7, 9)

    def migrate(self, dmd):
        # Remove unnecessary sub classes
        for path in BAD_PATHS:
            try:
                org = dmd.Events.getOrganizer(path)
            except Exception:
                continue
            dmd.Events.manage_deleteOrganizer(org.getDmdKey())

        # Remove unnecessary mappings
        # Kerberos
        krb_org = dmd.Events.getOrganizer('/Status/Kerberos')
        query = Or(Eq('id', KRB_INSTANCES[0]),
                   Eq('id', KRB_INSTANCES[1]),
                   Eq('id', KRB_INSTANCES[2]),
                   Eq('id', KRB_INSTANCES[3]),
                   Eq('id', KRB_INSTANCES[4]))
        krb_res = ICatalogTool(krb_org).search(EventClassInst, query=query)
        # Auth
        auth_org = dmd.Events.getOrganizer('/Status/Winrm/Auth')
        query = Or(Eq('id', AUTH_INSTANCES[0]),
                   Eq('id', AUTH_INSTANCES[1]),
                   Eq('id', AUTH_INSTANCES[2]))
        auth_res = ICatalogTool(auth_org).search(EventClassInst, query=query)
        if krb_res.total or auth_res.total:
            log.info('Removing unnecessary Event Class Instances')
            krb_org.removeInstances(KRB_INSTANCES)
            auth_org.removeInstances(AUTH_INSTANCES)
