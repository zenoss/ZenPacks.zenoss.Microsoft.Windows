##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
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
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.Zuul import listFacades, getFacade
from ZenPacks.zenoss.Microsoft.Windows.jobs import RemoveWinRMServices as RemoveWinRMServicesJob

log = logging.getLogger('zen.Microsoft.Windows.migrate.RemoveWinRMServices')
WARNING_MESSAGE = 'zenjobs must be stopped in order to fully complete the '\
                  'upgrade to version {} of the Microsoft Windows ZenPack! '\
                  'Please stop zenjobs and run the installation once more.  '\
                  'Alternatively, you can add the job manually.  '\
                  'This is necessary when upgrading from previous versions to'\
                  ' completely remove incompatible Windows Services.'\
                  ' If you have previously successfully installed this version'\
                  ' and/or all existing services in the winrmservices relationship'\
                  ' have been removed, no further action is necessary.'


class RemoveWinRMServices(ZenPackMigration):
    version = Version(2, 7, 2)

    def migrate(self, pack):
        log.info('Adding job to remove any leftover winrmservices.')
        if 'applications' in listFacades():
            from Products.ZenUtils.application import ApplicationState
            facade = getFacade('applications')
            for service in facade.queryMasterDaemons():
                if service.name == 'zenjobs' and service.state == ApplicationState.RUNNING:
                    log.warn(WARNING_MESSAGE.format(self.version.short()))
                    return
        else:
            zenhome = os.environ.get('ZENHOME', None)
            if zenhome:
                for f in os.listdir('{}/var'.format(zenhome)):
                    if re.match('zenjobs-.*\.pid', f):
                        log.warn(WARNING_MESSAGE.format(self.version.short()))
                        return

        pack.JobManager.addJob(RemoveWinRMServicesJob)
