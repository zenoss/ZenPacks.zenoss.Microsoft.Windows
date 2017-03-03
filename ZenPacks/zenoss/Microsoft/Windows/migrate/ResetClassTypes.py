##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""Reset meta_type and portal_type for objects that need it."""

import logging
import os
import re

# Zenoss Imports
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration, ZenPackException
from Products.Zuul import listFacades, getFacade
from ZenPacks.zenoss.Microsoft.Windows.jobs import ResetClassTypes as ResetClassTypesJob

log = logging.getLogger('zen.Microsoft.Windows.migrate.ResetClassTypes')
ERROR_MESSAGE = 'Stopping install.  zenjobs must be stopped before installing'\
                ' this version of the Microsoft Windows ZenPack!'


class ResetClassTypes(ZenPackMigration):
    version = Version(2, 7, 0)

    def migrate(self, pack):
        log.info('Adding job to reset class types for Windows devices')
        if 'applications' in listFacades():
            from Products.ZenUtils.application import ApplicationState
            facade = getFacade('applications')
            for service in facade.queryMasterDaemons():
                if service.name == 'zenjobs' and service.state == ApplicationState.RUNNING:
                    raise ZenPackException(ERROR_MESSAGE)
        else:
            zenhome = os.environ.get('ZENHOME', None)
            if zenhome:
                for f in os.listdir('{}/var'.format(zenhome)):
                    if re.match('zenjobs-.*\.pid', f):
                        raise ZenPackException(ERROR_MESSAGE)

        pack.JobManager.addJob(ResetClassTypesJob)
