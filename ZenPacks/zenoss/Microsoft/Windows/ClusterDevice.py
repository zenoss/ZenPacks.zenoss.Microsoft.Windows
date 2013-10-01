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

from Products.ZenRelations.RelSchema import ToManyCont, ToOne
from Products.Zuul.catalog.events import IndexingEvent
from Products.ZenUtils.IpUtil import getHostByName

from ZenPacks.zenoss.Microsoft.Windows.Device import Device as BaseDevice


class ClusterDevice(BaseDevice):
    """
    
    """

    clusterhostdevices = ''

    _properties = BaseDevice._properties + (
        {'id': 'clusterhostdevices', 'type': 'string', 'mode': 'w'},
        {'id': 'guid', 'type': 'string', 'mode': 'w'},
        {'id': 'creatingdc', 'type': 'string', 'mode': 'w'},
        )

    _relations = BaseDevice._relations + (
        ('clusterservices', ToManyCont(ToOne,
            'ZenPacks.zenoss.Microsoft.Windows.ClusterService',
            'cluster')),
        )

    def setClusterHostMachine(self, clusterhostdnsnames):

        for clusterhostdnsname in clusterhostdnsnames:
            deviceRoot = self.dmd.getDmdRoot("Devices")
            device = deviceRoot.findDeviceByIdOrIp(clusterhostdnsname)
            if device:
                # Server device in cluster already exists
                self.clusterhostdevices = clusterhostdnsnames
                return

            clusterhostip = getHostByName(clusterhostdnsname)

            @transact
            def create_device():
                # Need to create cluster server device
                dc = self.dmd.Devices.getOrganizer('/Devices/Server/Microsoft/Windows')

                clusterhost = dc.createInstance(clusterhostdnsname)
                clusterhost.manageIp = clusterhostip
                clusterhost.title = clusterhostdnsname
                clusterhost.setPerformanceMonitor(self.getPerformanceServerName())
                clusterhost.index_object()
                notify(IndexingEvent(clusterhost))

            create_device()
            clusterhost = deviceRoot.findDeviceByIdOrIp(clusterhostdnsname)
            clusterhost.collectDevice(setlog=False, background=True)

        self.clusterhostdevices = clusterhostdnsnames

    def getClusterHostMachine(self):
        clusterhostdevices = []
        for clusterhostdnsname in self.clusterhostdevices:
            deviceRoot = self.dmd.getDmdRoot("Devices")
            clusterhostdevices.append(deviceRoot.findDeviceByIdOrIp(clusterhostdnsname))
        return clusterhostdevices


class DeviceLinkProvider(object):
    '''
    Provides a link to the cluster server hosted on this device
    '''
    def __init__(self, device):
        self.device = device

    def getExpandedLinks(self):
        links = []

        hosts = self.device.getClusterHostMachine()

        if hosts:
            for host in hosts:
                links.append(
                    'Clustered Host: <a href="{}">{}</a>'.format(
                        host.getPrimaryUrlPath(),
                        host.titleOrId()
                        )
                    )

        return links

InitializeClass(ClusterDevice)
