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
from ZenPacks.zenoss.Microsoft.Windows.WinIIS import WinIIS
from ZenPacks.zenoss.Microsoft.Windows.WinService import WinService


class Device(BaseDevice):
    '''
    Model class for a Windows operating system device.
    '''

    clusterdevices = ''
    sqlhostname = None
    msexchangeversion = None
    ip_and_hostname = None
    domain_controller = False

    _properties = BaseDevice._properties + (
        {'id': 'clusterdevices', 'label': 'Cluster Devices', 'type': 'string', 'mode': 'w'},
        {'id': 'sqlhostname', 'label': 'SQL Host Name', 'type': 'string', 'mode': 'w'},
        {'id': 'msexchangeversion', 'label': 'MS Exchange Version', 'type': 'string', 'mode': 'w'},
        {'id': 'ip_and_hostname', 'type': 'string'},
        {'id': 'domain_controller', 'label': 'Domain Controller', 'type': 'boolean'},
    )

    def getPingStatus(self):
        return self.getStatus('/Status/Winrm/Ping')

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

    def is_iis(self):
        '''Return True if an IIS server'''
        # if we have IIS components, then we are IIS server
        for component in self.getDeviceComponents():
            if isinstance(component, WinIIS):
                return True
        return False

    def is_ntds(self):
        '''Return True if an NTDS/AD server'''
        # redundancy check domain_controller in case of LPU not returning NTDS or no services modeled
        if self.domain_controller:
            return True
        return False

    def is_exchange(self):
        '''return True if this is an Exchange server'''
        if self.msexchangeversion:
            return True
        return False

    def getRRDTemplates(self):
        """
        Returns all the templates bound to this Device and
        add MSExchangeIS or Active Directory template according to version.
        """
        templates = []
        for template in super(Device, self).getRRDTemplates():
            # skip IIS template if not installed
            if 'IIS' in template.id and not self.is_iis():
                continue
            if 'Active Directory' in template.id:
                # skip Active Director template if not installed
                if not self.is_ntds():
                    continue
                # get version-appropriate template
                if '2003' in self.getOSProductName():
                    template = self.getRRDTemplateByName('Active Directory 2003')
            if 'MSExchange' in template.id:
                # skip Exchange template if not installed
                if not self.is_exchange():
                    continue
                # get version-appropriate template
                exch = self.getRRDTemplateByName(self.msexchangeversion)
                if exch:
                    template = exch
            templates.append(template)

        return templates


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
