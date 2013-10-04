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

from Products.ZenModel.ZenStatus import ZenStatus
from Products.ZenModel.ManagedEntity import ManagedEntity
from Products.Zuul.catalog.events import IndexingEvent
from Products.ZenUtils.IpUtil import getHostByName

from ZenPacks.zenoss.Microsoft.Windows.Device import Device as BaseDevice
from ZenPacks.zenoss.Microsoft.Windows.OperatingSystem import OperatingSystem
from ZenPacks.zenoss.Microsoft.Windows.Hardware import Hardware


class ClusterDevice(BaseDevice):
    """
    
    """

    clusterhostdevices = ''
    guid = None
    creatingdc = None

    _properties = BaseDevice._properties + (
        {'id': 'clusterhostdevices', 'type': 'string', 'mode': 'w'},
        {'id': 'guid', 'type': 'string', 'mode': 'w'},
        {'id': 'creatingdc', 'type': 'string', 'mode': 'w'},
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

        if hasattr(self, '_create_componentSearch'):
            self._create_componentSearch()

    def setClusterHostMachines(self, clusterhostdnsnames):
        deviceRoot = self.dmd.getDmdRoot("Devices")
        for clusterhostdnsname in clusterhostdnsnames:
            clusterhostip = getHostByName(clusterhostdnsname)
            if clusterhostip:
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
                # create_device method above. Once this has been worked out
                # we will uncomment this code.
                #clusterhost = deviceRoot.findDeviceByIdOrIp(clusterhostdnsname)
                #clusterhost.collectDevice(setlog=False, background=True)

        self.clusterhostdevices = clusterhostdnsnames

    def getClusterHostMachines(self):
        _clusterhostdevice = []
        deviceRoot = self.dmd.getDmdRoot("Devices")
        for clusterhostdnsname in self.clusterhostdevices:
            clusterhostip = getHostByName(clusterhostdnsname)
            if clusterhostip:
                _clusterhostdevice.append(deviceRoot.findDeviceByIdOrIp(clusterhostip))
        return _clusterhostdevice


InitializeClass(ClusterDevice)
