##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from socket import gaierror

from Products.ZenUtils.IpUtil import getHostByName
from Products.Zuul import getFacade

from . import schema


class ClusterDevice(schema.ClusterDevice):
    '''
    Model class for a Windows virtual cluster device.
    '''

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
        self.LOG.info('Hostnames {0}'.format(clusterhostdnsnames))
        deviceRoot = self.dmd.getDmdRoot("Devices")
        for clusterhostdnsname in clusterhostdnsnames.keys():
            clusterhostip = clusterhostdnsnames[clusterhostdnsname]

            if not clusterhostip:
                try:
                    clusterhostip = getHostByName(clusterhostdnsname)
                except(gaierror):
                    self.LOG.warning('Unable to resolve hostname {0}'.format(clusterhostdnsname))
                    continue

            if deviceRoot.findDeviceByIdOrIp(clusterhostip) or \
                    deviceRoot.findDeviceByIdExact(clusterhostdnsname):
                # Server device in cluster already exists
                self.clusterhostdevices = clusterhostdnsnames.keys()
                self.clusterhostdevicesdict = clusterhostdnsnames
                continue

            def create_device():
                # Need to create cluster server device
                path = getattr(self, 'zWinRMClusterNodeClass', '/Devices/Server/Microsoft/Windows')
                try:
                    dc = self.dmd.Devices.getOrganizer(path)
                except KeyError:
                    dc = self.dmd.Devices.createOrganizer(path)
                fac = getFacade('device')
                fac.addDevice(clusterhostdnsname,
                              path,
                              title=clusterhostdnsname,
                              manageIp=clusterhostip,
                              model=True,
                              collector=self.getPerformanceServerName(),
                              zProperties={'zWinRMUser': self.zWinRMUser,
                                           'zWinRMPassword': self.zWinRMPassword,
                                           'zWinRMPort': self.zWinRMPort,
                                           'zWinKDC': self.zWinKDC,
                                           })

            create_device()
            # TODO (rbooth@zenoss.com):
            # The collectDevice method may hit a race condition with the
            # create_device method above.
            clusterhost = deviceRoot.findDeviceByIdOrIp(clusterhostdnsname)
            if clusterhost:
                clusterhost.collectDevice(setlog=False, background=True)

        self.clusterhostdevices = clusterhostdnsnames.keys()
        self.clusterhostdevicesdict = clusterhostdnsnames

    def getClusterHostMachines(self):
        return self.clusterhostdevices

    def setClusterHostMachinesList(self, value):
        '''
        Don't do anything.
        '''
        pass

    def getClusterHostMachinesList(self):
        '''
        Get hostnames of servers belonging to this cluster.
        '''
        _clusterhostdevice = []
        deviceRoot = self.dmd.getDmdRoot("Devices")
        for clusterhostdnsname in self.clusterhostdevices:
            try:
                clusterhostip = self.clusterhostdevicesdict[clusterhostdnsname]
            except (KeyError, AttributeError):
                if not hasattr(self, 'clusterhostdevicedict'):
                    self.clusterhostdevicesdict = {}
                try:
                    clusterhostip = self.clusterhostdevicesdict[clusterhostdnsname] = getHostByName(clusterhostdnsname)
                except(gaierror):
                    _clusterhostdevice.append('Unable to resolve hostname {0}'.format(clusterhostdnsname))
                    continue
            _clusterhostdevice.append(deviceRoot.findDeviceByIdOrIp(clusterhostip))
        return _clusterhostdevice

    def all_clusterhosts(self):
        ''''''
        deviceRoot = self.dmd.getDmdRoot("Devices")
        for host in self.getClusterHostMachines():
            clusterhost = deviceRoot.findDeviceByIdOrIp(host)
            if clusterhost:
                yield clusterhost

    def all_winsqlavailabilitygroups(self):
        """Generate all WinSQLAvailabilityGroup components."""
        for c in self.os.winsqlavailabilitygroups():
            yield c
