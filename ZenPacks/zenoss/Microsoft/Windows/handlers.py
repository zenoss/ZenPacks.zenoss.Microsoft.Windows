##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from zope.component import adapter
from OFS.interfaces import IObjectWillBeMovedEvent
from OFS.event import ObjectWillBeRemovedEvent

from datasources.ServiceDataSource import ServiceDataSource
from jobs import ReindexWinServices

DEFAULT_SERVICE = '/zport/dmd/Devices/Server/Microsoft/rrdTemplates/WinService/datasources/DefaultService'


@adapter(ServiceDataSource, IObjectWillBeMovedEvent)
def onServiceDataSourceMoved(ob, event):
    if isinstance(event, ObjectWillBeRemovedEvent):
        dmd = ob.getDmdRoot("Devices")
        if dmd:
            dmd.JobManager.addJob(ReindexWinServices, kwargs=dict(uid=DEFAULT_SERVICE))
