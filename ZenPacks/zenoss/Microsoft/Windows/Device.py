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

from socket import gaierror

from zope.event import notify
from ZODB.transact import transact

from Products.Zuul.interfaces import ICatalogTool
from Products.Zuul.catalog.events import IndexingEvent
from Products.ZenUtils.IpUtil import getHostByName

from ZenPacks.zenoss.Microsoft.Windows.zope_utils import BaseDevice


class Device(BaseDevice):
    '''
    Model class for a Windows operating system device.
    '''

    clusterdevices = ''
    sqlhostname = None
    msexchangeversion = None
    ip_and_hostname = None

    _properties = BaseDevice._properties + (
        {'id': 'clusterdevices', 'label': 'Cluster Devices', 'type': 'string', 'mode': 'w'},
        {'id': 'sqlhostname', 'label': 'SQL Host Name', 'type': 'string', 'mode': 'w'},
        {'id': 'msexchangeversion', 'label': 'MS Exchange Version', 'type': 'string', 'mode': 'w'},
        {'id': 'ip_and_hostname', 'type': 'string'},
    )

    def setClusterMachines(self, clusterdnsnames):
        '''
        Set cluster hostnames of which this server is a member.
        '''
        deviceRoot = self.dmd.getDmdRoot("Devices")
        for clusterdnsname in clusterdnsnames:
            try:
                clusterip = getHostByName(clusterdnsname)
            except(gaierror):
                log.warning(
                    'Unable to resolve hostname {0}'.format(clusterdnsname)
                )
                continue

            device = deviceRoot.findDeviceByIdOrIp(clusterip)
            if device:
                # Cluster device already exists
                self.clusterdevices = clusterdnsnames
                continue

            @transact
            def create_device():
                # Need to create cluster device
                dc = self.dmd.Devices.getOrganizer(
                    '/Devices/Server/Microsoft/Cluster'
                )

                cluster = dc.createInstance(clusterdnsname)
                cluster.manageIp = clusterip
                cluster.title = clusterdnsname
                cluster.setPerformanceMonitor(self.getPerformanceServerName())
                # Transfer settings to newly created cluster device
                cluster.zCollectorPlugins.append('zenoss.winrm.WinCluster')
                cluster.setZenProperty('zWinRMUser', self.zWinRMUser)
                cluster.setZenProperty('zWinRMPassword', self.zWinRMPassword)
                cluster.setZenProperty('zWinRMPort', self.zWinRMPort)
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
        return self.clusterdevices

    def setClusterMachinesList(self, value):
        '''
        Don't do anything.
        '''
        pass

    def getClusterMachinesList(self):
        '''
        Get cluster hostnames of which this server is a member.
        '''
        _clusterdevices = []
        deviceRoot = self.dmd.getDmdRoot("Devices")
        for clusterdnsname in self.clusterdevices:
            try:
                clusterip = getHostByName(clusterdnsname)
                _clusterdevices.append(
                    deviceRoot.findDeviceByIdOrIp(clusterip)
                )
            except(gaierror):
                _clusterdevices.append('Unable to resolve hostname {0}'.format(
                    clusterdnsname))
        return _clusterdevices

    def getRRDTemplates(self):
        """
        Returns all the templates bound to this Device and
        add MSExchangeIS or Active Directory template according to version.
        """
        result = super(Device, self).getRRDTemplates()
        # Check if version of the system
        # modeled by OperatingSystem plugin is Windows 2003.
        # https://jira.hyperic.com/browse/HHQ-5553
        if '2003' in self.getOSProductName():
            for template in result:
                ad = self.getRRDTemplateByName('Active Directory 2003')
                if ad:
                    if 'Active Directory' in template.id:
                        result[result.index(template)] = ad
        if self.msexchangeversion:
            for template in result:
                exchange = self.getRRDTemplateByName(self.msexchangeversion)
                if exchange:
                    if 'MSExchange' in template.id:
                        result[result.index(template)] = exchange
        return result


class DeviceLinkProvider(object):
    '''
    Provides a link to the cluster server hosted on this device
    '''
    def __init__(self, device):
        self.device = device

    def getExpandedLinks(self):
        links = []
        try:
            hosts = self.device.getClusterHostMachinesList()
            if hosts:
                for host in hosts:
                    links.append(
                        'Node: <a href="{}">{}</a>'.format(
                            host.getPrimaryUrlPath(),
                            host.titleOrId()
                        )
                    )
        except(AttributeError):
            pass

        try:
            clusters = self.device.getClusterMachinesList()
            if clusters:
                for cluster in clusters:
                    links.append(
                        'Cluster: <a href="{}">{}</a>'.format(
                            cluster.getPrimaryUrlPath(),
                            cluster.titleOrId()
                        )
                    )
        except(AttributeError):
            pass

        # Look up for HyperV server with same IP
        try:
            dc = self.device.getDmdRoot('Devices').getOrganizer(
                '/Server/Microsoft/HyperV')

            results = ICatalogTool(dc).search(
                types=(
                    'ZenPacks.zenoss.Microsoft.HyperV.HyperVVSMS.HyperVVSMS',
                )
            )
            for brain in results:
                obj = brain.getObject()
                id_list = self.device.ip_and_hostname or [self.device.id]
                if obj.ip in id_list:
                    links.append(
                        'Hyper-V Server: <a href="{}">{}</a>'.format(
                            obj.getPrimaryUrlPath(),
                            obj.titleOrId()
                        )
                    )
        except Exception:
            pass

        return links
