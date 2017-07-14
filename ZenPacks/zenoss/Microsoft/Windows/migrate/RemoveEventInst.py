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
from Products.AdvancedQuery import In
from Products.ZenEvents.EventClassInst import EventClassInst

log = logging.getLogger('zen.Microsoft.Windows.migrate.RemoveEventInst')
BAD_PATHS = (
    '/Status/Kerberos/Auth',
    '/Status/Kerberos/Failure',
    '/Status/Winrm',
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
WIN_INSTANCES = (
    'WindowsServiceLog',
    'IISSiteStatus')
PATH_INSTANCES = {
    '/Status/Kerberos': KRB_INSTANCES,
    '/Status/Winrm/Auth': AUTH_INSTANCES,
    '/Status': WIN_INSTANCES
}


class RemoveEventInst(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 7, 9)

    def migrate(self, dmd):
        # Remove unnecessary sub classes
        log.info('Searching for deprecated Event Class subclasses and mappings to remove.')
        for path in BAD_PATHS:
            try:
                org = dmd.Events.getOrganizer(path)
            except Exception:
                continue
            dmd.Events.manage_deleteOrganizer(org.getDmdKey())

        # Remove unnecessary mappings
        def remove_mapping(path, instances):
            try:
                org = dmd.Events.getOrganizer(path)
                results = ICatalogTool(org).search(EventClassInst, query=In('id', instances))
                if results.total:
                    log.info('Removing deprecated Event Class Instances from {}'.format(path))
                    org.removeInstances(instances)
            except Exception:
                pass

        for path, instances in PATH_INSTANCES.iteritems():
            remove_mapping(path, instances)
