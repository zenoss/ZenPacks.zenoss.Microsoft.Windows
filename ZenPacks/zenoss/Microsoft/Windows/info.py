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
from Products.Zuul.infos.component.winservice import WinServiceInfo
from ZenPacks.zenoss.Microsoft.Windows.interfaces import *
from ZenPacks.zenoss.Microsoft.Windows.interfaces import IFileSystemInfo as WIFileSystemInfo


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
    sqlhostname = ProxyProperty('sqlhostname')
    msexchangeversion = ProxyProperty('msexchangeversion')
    ip_and_hostname = ProxyProperty('ip_and_hostname')


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


class FileSystemInfo(ComponentInfo):
    implements(WIFileSystemInfo)

    mount = ProxyProperty('mount')
    storageDevice = ProxyProperty('storageDevice')
    type = ProxyProperty('type')
    blockSize = ProxyProperty('blockSize')
    totalBlocks = ProxyProperty('totalBlocks')
    totalFiles = ProxyProperty('totalFiles')
    maxNameLength = ProxyProperty('maxNameLen')

    @property
    def totalBytes(self):
        return self._object.totalBytes()

    @property
    def usedBytes(self):
        return self._object.usedBytes()

    @property
    def availableBytes(self):
        return self._object.availBytes()

    @property
    def capacityBytes(self):
        return self._object.capacity()

    @property
    def availableFiles(self):
        return self._object.availFiles()

    @property
    def capacityFiles(self):
        return self._object.inodeCapacity()

    mediatype = ProxyProperty('mediatype')


class WinServiceInfo(WinServiceInfo):
    implements(IWinServiceInfo)

    usermonitor = ProxyProperty('usermonitor')

    def getMonitor(self):
        monitorstatus = self._object.monitored()
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
    cluster_node_server = ProxyProperty('cluster_node_server')
    systemobject = ProxyProperty('systemobject')
    recoverymodel = ProxyProperty('recoverymodel')
    status = ProxyProperty('status')

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
    cluster_node_server = ProxyProperty('cluster_node_server')


class ClusterServiceInfo(WinComponentInfo):
    implements(IClusterServiceInfo)
    ownernode = ProxyProperty('ownernode')
    description = ProxyProperty('description')
    coregroup = ProxyProperty('coregroup')
    priority = ProxyProperty('priority')

    @property
    @info
    def state(self):
        return self._object.getState()

    @property
    @info
    def clusternode(self):
        entity = self._object.ownernodeentity()
        if entity:
            return '<a class="z-entity" href="{}">{}</a>'.format(
                entity.getPrimaryUrlPath(), self._object.ownernode)
        return self._object.ownernode


class ClusterResourceInfo(WinComponentInfo):
    implements(IClusterResourceInfo)
    ownernode = ProxyProperty('ownernode')
    description = ProxyProperty('description')
    ownergroup = ProxyProperty('ownergroup')

    @property
    @info
    def state(self):
        return self._object.getState()

    @property
    @info
    def servicegroup(self):
        return self._object.clusterservice()

    @property
    @info
    def clusternode(self):
        entity = self._object.ownernodeentity()
        if entity:
            return '<a class="z-entity" href="{}">{}</a>'.format(
                entity.getPrimaryUrlPath(), self._object.ownernode)
        return self._object.ownernode


class ClusterNodeInfo(WinComponentInfo):
    implements(IClusterNodeInfo)
    assignedvote = ProxyProperty('assignedvote')
    currentvote = ProxyProperty('currentvote')

    @property
    @info
    def state(self):
        return self._object.getState()

    @property
    @info
    def clusternode(self):
        entity = self._object.ownernodeentity()
        if entity:
            return '<a class="z-entity" href="{}">{}</a>'.format(
                entity.getPrimaryUrlPath(), self._object.title)
        return self._object.title


class ClusterDiskInfo(WinComponentInfo):
    implements(IClusterDiskInfo)
    volumepath = ProxyProperty('volumepath')
    ownernode = ProxyProperty('ownernode')
    disknumber = ProxyProperty('disknumber')
    partitionnumber = ProxyProperty('partitionnumber')
    size = ProxyProperty('size')
    freespace = ProxyProperty('freespace')
    assignedto = ProxyProperty('assignedto')

    @property
    @info
    def state(self):
        return self._object.getState()

    @property
    @info
    def clusternode(self):
        return self._object.clusternode()


class ClusterNetworkInfo(WinComponentInfo):
    implements(IClusterNetworkInfo)
    description = ProxyProperty('description')
    role = ProxyProperty('role')

    @property
    @info
    def state(self):
        return self._object.getState()


class ClusterInterfaceInfo(WinComponentInfo):
    implements(IClusterInterfaceInfo)
    node = ProxyProperty('node')
    network = ProxyProperty('network')
    ipaddresses = ProxyProperty('ipaddresses')
    adapter = ProxyProperty('adapter')

    @property
    @info
    def state(self):
        return self._object.getState()

    @property
    @info
    def clusternode(self):
        return self._object.clusternode()

    @property
    @info
    def clusternetwork(self):
        networks = self._object.clusternetworks()
        for network in networks:
            if network.title == self._object.network:
                return network


class WinSQLJobInfo(WinComponentInfo):
    implements(IWinSQLJobInfo)

    instancename = ProxyProperty('instancename')
    jobid = ProxyProperty('jobid')
    enabled = ProxyProperty('enabled')
    description = ProxyProperty('description')
    username = ProxyProperty('username')
    datecreated = ProxyProperty('datecreated')
    cluster_node_server = ProxyProperty('cluster_node_server')

    @property
    @info
    def instance(self):
        return self._object.winsqlinstance()

    def getMonitor(self):
        monitorstatus = self._object.monitored()
        return monitorstatus

    def setMonitor(self, value):
        self._object.monitor = value
        self._object.index_object()

    monitor = property(getMonitor, setMonitor)
