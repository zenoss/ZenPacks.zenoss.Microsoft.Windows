##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


import logging
LOG = logging.getLogger("zen.MicrosoftWindows")

from socket import gaierror

from zope.event import notify
from ZODB.transact import transact

from Products.Zuul.catalog.events import IndexingEvent
from Products.ZenUtils.IpUtil import getHostByName

from ZenPacks.zenoss.Microsoft.Windows.Device import Device as BaseDevice


class ClusterDevice(BaseDevice):
    '''
    Model class for a Windows virtual cluster device.
    '''

    clusterhostdevices = ''
    guid = None
    creatingdc = None

    _properties = BaseDevice._properties + (
        {'id': 'clusterhostdevices', 'type': 'string', 'mode': 'w'},
        {'id': 'guid', 'type': 'string', 'mode': 'w'},
        {'id': 'creatingdc', 'type': 'string', 'mode': 'w'},
        )

    def setClusterMachines(self, clusterdnsnames):
        '''
        Don't do anything. Overridden from BaseDevice.
        '''
        self.clusterdevices = clusterdnsnames

    def getClusterMachines(self):
        '''
        Return what was previously set.
        '''
        return self.clusterdevices

    def setClusterHostMachines(self, clusterhostdnsnames):
        '''
        Set hostnames of servers belonging to this cluster.
        '''
        LOG.info('Hostnames {0}'.format(clusterhostdnsnames))
        deviceRoot = self.dmd.getDmdRoot("Devices")
        for clusterhostdnsname in clusterhostdnsnames:
            try:
                clusterhostip = getHostByName(clusterhostdnsname)
            except(gaierror):
                LOG.warning('Unable to resolve hostname {0}'.format(clusterhostdnsname))
                return

            device = deviceRoot.findDeviceByIdOrIp(clusterhostip)
            if device:
                # Server device in cluster already exists
                self.clusterhostdevices = clusterhostdnsnames
                return

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
            # TODO (rbooth@zenoss.com):
            # The collectDevice method may hit a race condition with the
            # create_device method above.
            clusterhost = deviceRoot.findDeviceByIdOrIp(clusterhostdnsname)
            if clusterhost:
                clusterhost.collectDevice(setlog=False, background=True)

        self.clusterhostdevices = clusterhostdnsnames

    def getClusterHostMachines(self):
        '''
        Get hostnames of servers belonging to this cluster.
        '''
        _clusterhostdevice = []
        deviceRoot = self.dmd.getDmdRoot("Devices")
        for clusterhostdnsname in self.clusterhostdevices:
            try:
                clusterhostip = getHostByName(clusterhostdnsname)
                _clusterhostdevice.append(deviceRoot.findDeviceByIdOrIp(clusterhostip))
            except(gaierror):
                _clusterhostdevice.append('Unable to resolve hostname {0}'.format(
                    clusterhostdnsname))
        return _clusterhostdevice
