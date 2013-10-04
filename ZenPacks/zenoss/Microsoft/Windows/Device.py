##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


import logging
log = logging.getLogger("zen.MicrosoftWindows")

from Globals import InitializeClass

from zope.event import notify

from ZODB.transact import transact

from Products.ZenModel.Device import Device as BaseDevice
from Products.ZenModel.ManagedEntity import ManagedEntity
from Products.ZenModel.ZenStatus import ZenStatus
from Products.Zuul.catalog.events import IndexingEvent
from Products.ZenUtils.IpUtil import getHostByName

from ZenPacks.zenoss.Microsoft.Windows.OperatingSystem import OperatingSystem
from ZenPacks.zenoss.Microsoft.Windows.Hardware import Hardware


class Device(BaseDevice):
    """
    A device class that knows about enclosures
    """

    clusterdevices = ''

    _properties = BaseDevice._properties + (
        {'id': 'clusterdevices', 'type': 'string', 'mode': 'w'},
        )

    def __init__(self, id, buildRelations=True):
        ManagedEntity.__init__(self, id, buildRelations=buildRelations)

        os = OperatingSystem()
        self._setObject(os.id, os)

        hw = Hardware()
        self._setObject(hw.id, hw)

        self._lastPollSnmpUpTime = ZenStatus(0)
        self._snmpLastCollection = 0
        self._lastChange = 0

    def setClusterMachines(self, clusterdnsnames):

        deviceRoot = self.dmd.getDmdRoot("Devices")
        for clusterdnsname in clusterdnsnames:
            clusterip = getHostByName(clusterdnsname)

            if clusterip:
                device = deviceRoot.findDeviceByIdOrIp(clusterip)
                if device:
                    # Cluster device already exists
                    self.clusterdevices = clusterdnsnames
                    return

                @transact
                def create_device():
                    # Need to create cluster device
                    dc = self.dmd.Devices.getOrganizer('/Devices/Server/Microsoft/Cluster')

                    cluster = dc.createInstance(clusterdnsname)
                    cluster.manageIp = clusterip
                    cluster.title = clusterdnsname
                    cluster.setPerformanceMonitor(self.getPerformanceServerName())
                    cluster.index_object()
                    notify(IndexingEvent(cluster))

                create_device()
                # TODO (rbooth@zenoss.com):
                # The collectDevice method may hit a race condition with the
                # create_device method above.
                cluster = deviceRoot.findDeviceByIdOrIp(clusterdnsname)
                if cluster:
                    cluster.collectDevice(setlog=False, background=True)

        self.clusterdevices = clusterdnsnames

    def getClusterMachines(self):
        _clusterdevices = []
        deviceRoot = self.dmd.getDmdRoot("Devices")
        for clusterdnsname in self.clusterdevices:
            clusterip = getHostByName(clusterdnsname)
            if clusterip:
                _clusterdevices.append(deviceRoot.findDeviceByIdOrIp(clusterip))
        return _clusterdevices


class DeviceLinkProvider(object):
    '''
    Provides a link to the cluster server hosted on this device
    '''
    def __init__(self, device):
        self.device = device

    def getExpandedLinks(self):
        links = []

        try:
            hosts = self.device.getClusterHostMachines()
            if hosts:
                for host in hosts:
                    links.append(
                        'Clustered Host: <a href="{}">{}</a>'.format(
                            host.getPrimaryUrlPath(),
                            host.titleOrId()
                            )
                        )
        except(AttributeError):
            pass

        clusters = self.device.getClusterMachines()
        if clusters:
            for cluster in clusters:
                links.append(
                    'Clustered Server: <a href="{}">{}</a>'.format(
                        cluster.getPrimaryUrlPath(),
                        cluster.titleOrId()
                        )
                    )

        return links

InitializeClass(Device)
