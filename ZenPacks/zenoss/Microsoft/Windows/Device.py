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

    def setClusterMachine(self, clusterdnsnames):

        for clusterdnsname in clusterdnsnames:
            deviceRoot = self.dmd.getDmdRoot("Devices")
            device = deviceRoot.findDeviceByIdExact(clusterdnsname)
            if device:
                # Cluster device already exists
                return

            clusterip = getHostByName(clusterdnsname)
            cluster_om = []

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
                cluster_om.append(cluster)

            self.clusterdevices = cluster_om
            create_device()
            cluster = deviceRoot.findDeviceByIdExact(clusterdnsname)
            cluster.collectDevice(setlog=False, background=True)

    def getClusterMachine(self):
        return self.clusterdevices


class DeviceLinkProvider(object):
    '''
    Provides a link to this host on the overview screen of the Linux
    server device underlying this host.
    '''
    def __init__(self, device):
        self.device = device

    def getExpandedLinks(self):
        links = []

        hosts = self.device.getClusterMachine()

        if hosts:
            for host in hosts:
                links.append(
                    'Clustered Host: <a href="{}">{}</a>'.format(
                        #host.getPrimaryUrlPath(),
                        #host.titleOrId()
                        host, host)
                    )

        return links

InitializeClass(Device)
