##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Globals import InitializeClass
from socket import gaierror
import logging

from Products.ZenModel.OSComponent import OSComponent
from Products.ZenRelations.RelSchema import ToOne, ToManyCont
from Products.ZenUtils.IpUtil import getHostByName

from utils import cluster_state_string

log = logging.getLogger("zen.MicrosoftWindows")


class ClusterService(OSComponent):
    '''
    Model class for Cluster Service.
    '''
    meta_type = portal_type = 'MSClusterService'

    ownernode = None
    description = None
    coregroup = False
    priority = 0
    state = None
    domain = ""

    _properties = OSComponent._properties + (
        {'id': 'ownernode', 'label': 'Owner Node', 'type': 'string'},
        {'id': 'description', 'label': 'Description', 'type': 'string'},
        {'id': 'coregroup', 'label': 'Core Group', 'type': 'boolean'},
        {'id': 'priority', 'label': 'Priority', 'type': 'integer'},
        {'id': 'state', 'label': 'State', 'type': 'string'},
        {'id': 'domain', 'label': 'Domain', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ('os', ToOne(ToManyCont,
         'ZenPacks.zenoss.Microsoft.Windows.OperatingSystem', 'clusterservices')),
        ('clusterresources', ToManyCont(ToOne,
         'ZenPacks.zenoss.Microsoft.Windows.ClusterResource', 'clusterservice')),
    )

    def ownernodeentity(self):
        deviceRoot = self.dmd.getDmdRoot("Devices")
        try:
            clusterhostip = getHostByName(self.ownernode + "." + self.domain)
            return deviceRoot.findDeviceByIdOrIp(clusterhostip)
        except(gaierror):
            log.warning('Unable to resolve hostname {0}'.format(self.ownernode + "." + self.domain))
            return

    def getRRDTemplateName(self):
        return 'ClusterService'

    def getIconPath(self):
        '''
        Return the path to an icon for this component.
        '''
        return '/++resource++mswindows/img/ClusterService.png'

    def getState(self):
        try:
            state = int(self.cacheRRDValue('state', None))
        except Exception:
            return 'Unknown'

        return cluster_state_string(state)


InitializeClass(ClusterService)
