##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from zope.interface import implements
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.infos.component import ComponentInfo
from Products.Zuul.infos.device import DeviceInfo as BaseDeviceInfo
from Products.Zuul.infos.component.filesystem import FileSystemInfo as BaseFileSystemInfo
from Products.Zuul.infos.component.ipinterface import IpInterfaceInfo as BaseIpInterfaceInfo
from Products.Zuul.decorators import info

from ZenPacks.zenoss.Microsoft.Windows.interfaces import *


def SuffixedProperty(property_name, suffix):
    '''
    Return a read-only property with a value of property suffixed with
    suffix.
    '''
    def getter(self):
        value = getattr(self._object, property_name)
        if value is None:
            return 'n/a'

        return '{} {}'.format(value, suffix)

    return property(getter)


class DeviceInfo(BaseDeviceInfo):
    clusterdevices = ProxyProperty('clusterdevices')


class ClusterDeviceInfo(BaseDeviceInfo):
    clusterhostdevices = ProxyProperty('clusterhostdevices')
    guid = ProxyProperty('guid')
    creatingdc = ProxyProperty('creatingdc')


class WinComponentInfo(ComponentInfo):
    title = ProxyProperty('title')


class TeamInterfaceInfo(BaseIpInterfaceInfo):
    implements(ITeamInterfaceInfo)

    @property
    def nic_count(self):
        return self._object.teaminterfaces.countObjects()


class InterfaceInfo(BaseIpInterfaceInfo):
    implements(IInterfaceInfo)


class CPUInfo(WinComponentInfo):
    implements(ICPUInfo)

    description = ProxyProperty('description')
    socket = ProxyProperty('socket')
    cores = ProxyProperty('cores')
    threads = ProxyProperty('threads')
    clockspeed = ProxyProperty('clockspeed')
    extspeed = ProxyProperty('extspeed')
    voltage = ProxyProperty('voltage')
    cacheSizeL1 = ProxyProperty('cacheSizeL1')
    cacheSizeL2 = ProxyProperty('cacheSizeL2')
    cacheSpeedL2 = ProxyProperty('cacheSpeedL2')
    cacheSizeL3 = ProxyProperty('cacheSizeL3')
    cacheSpeedL3 = ProxyProperty('cacheSpeedL3')

    # String unit-suffixed versions of numeric properties.
    clockspeed_str = SuffixedProperty('clockspeed', 'MHz')
    extspeed_str = SuffixedProperty('extspeed', 'MHz')
    voltage_str = SuffixedProperty('voltage', 'mV')
    cacheSizeL1_str = SuffixedProperty('cacheSizeL1', 'KB')
    cacheSizeL2_str = SuffixedProperty('cacheSizeL2', 'KB')
    cacheSpeedL2_str = SuffixedProperty('cacheSpeedL2', 'MHz')
    cacheSizeL3_str = SuffixedProperty('cacheSizeL3', 'KB')
    cacheSpeedL3_str = SuffixedProperty('cacheSpeedL3', 'MHz')

    @property
    @info
    def manufacturer(self):
        pc = self._object.productClass()
        if pc:
            return pc.manufacturer()

    @property
    @info
    def product(self):
        return self._object.productClass()


class FileSystemInfo(BaseFileSystemInfo):
    implements(IFileSystemInfo)

    mediatype = ProxyProperty('mediatype')


class WinServiceInfo(WinComponentInfo):
    implements(IWinServiceInfo)

    servicename = ProxyProperty('servicename')
    caption = ProxyProperty('caption')
    description = ProxyProperty('description')
    startmode = ProxyProperty('startmode')
    account = ProxyProperty('account')
    usermonitor = ProxyProperty('usermonitor')

    def getMonitor(self):
        monitorstatus = self._object.getMonitor()
        return monitorstatus

    def setMonitor(self, value):
        self._object.usermonitor = True
        self._object.monitor = value
        self._object.index_object()

    monitor = property(getMonitor, setMonitor)


class WinIISInfo(WinComponentInfo):
    implements(IWinIISInfo)

    sitename = ProxyProperty('sitename')
    apppool = ProxyProperty('apppool')
    caption = ProxyProperty('caption')
    status = ProxyProperty('status')
    statusname = ProxyProperty('statusname')


class WinSQLBackupInfo(WinComponentInfo):
    implements(IWinSQLBackupInfo)

    devicetype = ProxyProperty('devicetype')
    physicallocation = ProxyProperty('physicallocation')
    status = ProxyProperty('status')
    instancename = ProxyProperty('instancename')

    @property
    @info
    def instance(self):
        return self._object.winsqlinstance()


class WinSQLDatabaseInfo(WinComponentInfo):
    implements(IWinSQLDatabaseInfo)

    instancename = ProxyProperty('instancename')
    version = ProxyProperty('version')
    owner = ProxyProperty('owner')
    isaccessible = ProxyProperty('isaccessible')
    collation = ProxyProperty('collation')
    createdate = ProxyProperty('createdate')
    defaultfilegroup = ProxyProperty('defaultfilegroup')
    primaryfilepath = ProxyProperty('primaryfilepath')

    @property
    def lastlogbackup(self):
        lastlogbackupdate = self._object.lastlogbackupdate

        if lastlogbackupdate == None:
            return 'No Log Backups'
        else:
            return lastlogbackupdate

    @property
    def lastbackup(self):
        lastbackupdate = self._object.lastbackupdate

        if lastbackupdate == None:
            return 'No Backups'
        else:
            return lastbackupdate

    @property
    @info
    def instance(self):
        return self._object.winsqlinstance()


class WinSQLInstanceInfo(WinComponentInfo):
    implements(IWinSQLInstanceInfo)
    instancename = ProxyProperty('instancename')


class ClusterServiceInfo(WinComponentInfo):
    implements(IClusterServiceInfo)
    ownernode = ProxyProperty('ownernode')
    description = ProxyProperty('description')
    coregroup = ProxyProperty('coregroup')
    priority = ProxyProperty('priority')
    state = ProxyProperty('state')

    @property
    def clusternode(self):
        return self._object.ownernodeurl()


class ClusterResourceInfo(WinComponentInfo):
    implements(IClusterResourceInfo)
    ownernode = ProxyProperty('ownernode')
    description = ProxyProperty('description')
    ownergroup = ProxyProperty('ownergroup')
    state = ProxyProperty('state')

    @property
    @info
    def servicegroup(self):
        return self._object.clusterservice()

    @property
    def clusternode(self):
        return self._object.ownernodeurl()


class WinSQLJobInfo(WinComponentInfo):
    implements(IWinSQLJobInfo)

    instancename = ProxyProperty('instancename')
    jobid = ProxyProperty('jobid')
    enabled = ProxyProperty('enabled')
    description = ProxyProperty('description')
    username = ProxyProperty('username')
    datecreated = ProxyProperty('datecreated')

    @property
    @info
    def instance(self):
        return self._object.winsqlinstance()
