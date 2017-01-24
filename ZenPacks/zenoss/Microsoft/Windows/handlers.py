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
    if isinstance(event, ObjectWillBeRemovedEvent):
        dmd = ob.getDmdRoot("Devices")
        template = ob.rrdTemplate().id
        temporary = [x for x in ['-new', '-backup', '-preupgrade'] if x in template]
        if dmd and not temporary:
            log.debug('handler: Starting ReindexWinServices job')
            dmd.JobManager.addJob(ReindexWinServices, kwargs=dict(uid=DEFAULT_SERVICE))
