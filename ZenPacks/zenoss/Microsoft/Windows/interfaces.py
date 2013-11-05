##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.Zuul.form import schema
from Products.Zuul.interfaces.device import IDeviceInfo
from Products.Zuul.interfaces.component import IComponentInfo
from Products.Zuul.interfaces.component import IIpInterfaceInfo as IBaseIpInterfaceInfo

from Products.Zuul.utils import ZuulMessageFactory as _t


class IDeviceInfo(IDeviceInfo):
    clusterdevices = schema.TextLine(title=_t(u'Cluster Devices'), readonly=True)


class IClusterDeviceInfo(IDeviceInfo):
    clusterhostdevices = schema.TextLine(title=_t(u'Cluster Host Devices'), readonly=True)
    guid = schema.TextLine(title=_t(u'GUID'), readonly=True)
    creatingdc = schema.TextLine(title=_t(u'Creating DC'), readonly=True)


class IWinComponentInfo(IComponentInfo):
    title = schema.TextLine(title=_t(u'Title'), readonly=True)


class ITeamInterfaceInfo(IBaseIpInterfaceInfo):
    pass


class IInterfaceInfo(IBaseIpInterfaceInfo):
    pass


class IWinServiceInfo(IWinComponentInfo):
    servicename = schema.TextLine(title=_t(u'Service Name'), readonly=True)
    caption = schema.TextLine(title=_t(u'Caption'), readonly=True)
    description = schema.TextLine(title=_t(u'Description'), readonly=True)
    startmode = schema.TextLine(title=_t(u'Start Mode'), readonly=True)
    account = schema.TextLine(title=_t(u'Account'), readonly=True)
    state = schema.TextLine(title=_t(u'Current State'), readonly=True)
    usermonitor = schema.TextLine(title=_t(u'User Selected Monitor State'), readonly=True)


class IWinIISInfo(IWinComponentInfo):
    sitename = schema.TextLine(title=_t(u'Site Name'), readonly=True)
    apppool = schema.TextLine(title=_t(u'App Pool'), readonly=True)
    caption = schema.TextLine(title=_t(u'Caption'), readonly=True)
    status = schema.TextLine(title=_t(u'Status'), readonly=True)
    statusname = schema.TextLine(title=_t(u'Status Name'), readonly=True)


class IWinSQLBackupInfo(IWinComponentInfo):
    devicetype = schema.TextLine(title=_t(u'Device Type'), readonly=True)
    physicallocation = schema.TextLine(title=_t(u'Physical Location'), readonly=True)
    status = schema.TextLine(title=_t(u'Status'), readonly=True)
    instancename = schema.TextLine(title=_t(u'Instance Name'), readonly=True)


class IWinSQLDatabaseInfo(IWinComponentInfo):
    instancename = schema.TextLine(title=_t(u'Instance Name'), readonly=True)
    version = schema.TextLine(title=_t(u'Version'), readonly=True)
    owner = schema.TextLine(title=_t(u'Owner'), readonly=True)
    lastbackup = schema.TextLine(title=_t(u'Last Backup'), readonly=True)
    lastlogbackup = schema.TextLine(title=_t(u'Last Log Backup'), readonly=True)
    isaccessible = schema.TextLine(title=_t(u'Accessible'), readonly=True)
    collation = schema.TextLine(title=_t(u'Collation'), readonly=True)
    createdate = schema.TextLine(title=_t(u'Created On'), readonly=True)
    defaultfilegroup = schema.TextLine(title=_t(u'File Group'), readonly=True)
    primaryfilepath = schema.TextLine(title=_t(u'File Path'), readonly=True)


class IWinSQLInstanceInfo(IWinComponentInfo):
    instancename = schema.TextLine(title=_t(u'Instance Name'), readonly=True)


class IClusterServiceInfo(IWinComponentInfo):
    ownernode = schema.TextLine(title=_t(u'Owner Node'), readonly=True)
    description = schema.TextLine(title=_t(u'Description'), readonly=True)
    coregroup = schema.TextLine(title=_t(u'Core Group'), readonly=True)
    priority = schema.TextLine(title=_t(u'Priority'), readonly=True)
    state = schema.TextLine(title=_t(u'State'), readonly=True)


class IClusterResourceInfo(IWinComponentInfo):
    ownernode = schema.TextLine(title=_t(u'Owner Node'), readonly=True)
    description = schema.TextLine(title=_t(u'Description'), readonly=True)
    ownergroup = schema.TextLine(title=_t(u'Owner Group'), readonly=True)
    state = schema.TextLine(title=_t(u'State'), readonly=True)


class IWinSQLJobInfo(IWinComponentInfo):
    instancename = schema.TextLine(title=_t(u'Instance Name'), readonly=True)
    jobid = schema.TextLine(title=_t(u'Job ID'), readonly=True)
    enabled = schema.TextLine(title=_t(u'Enabled'), readonly=True)
    description = schema.TextLine(title=_t(u'Description'), readonly=True)
    username = schema.TextLine(title=_t(u'User'), readonly=True)
    datecreated = schema.TextLine(title=_t(u'Date Created'), readonly=True)
