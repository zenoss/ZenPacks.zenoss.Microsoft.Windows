##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from zope.component import adapter
from OFS.interfaces import IObjectWillBeMovedEvent
from OFS.event import ObjectWillBeRemovedEvent

from datasources.ServiceDataSource import ServiceDataSource
from jobs import ReindexWinServices

log = logging.getLogger('zen.MicrosoftWindows')
DEFAULT_SERVICE = '/zport/dmd/Devices/Server/Microsoft/rrdTemplates/WinService/datasources/DefaultService'


@adapter(ServiceDataSource, IObjectWillBeMovedEvent)
def onServiceDataSourceMoved(ob, event):
    """Run ReindexWinServices job on template removal
    Do not run if removing a temporary template used by ZenPackLib during
    install/remove of the ZenPack.
    Do not run if there are pending Reindex jobs.
    Do not run during ZenPack installation/removal
    """
    if isinstance(event, ObjectWillBeRemovedEvent):
        dmd = ob.getDmdRoot("Devices")
        pack = dmd.ZenPackManager.packs._getOb('ZenPacks.zenoss.Microsoft.Windows')
        for attribute in ('in_install', 'in_remove'):
            if hasattr(pack, attribute):
                if getattr(pack, attribute):
                    return
        try:
            template = ob.rrdTemplate().id
            temporary = [x for x in ['-new', '-backup', '-preupgrade'] if x in template]
        except Exception:
            temporary = False

        if dmd and not temporary:
            for job in dmd.JobManager.getPendingJobs():
                if job.type == ReindexWinServices.getJobType():
                    log.debug('handler: ReindexWinServices already pending')
                    return

            log.debug('handler: Starting ReindexWinServices job')
            dmd.JobManager.addJob(ReindexWinServices, kwargs=dict(uid=DEFAULT_SERVICE))
