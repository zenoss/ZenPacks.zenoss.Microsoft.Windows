##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
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


class ClusterNode(OSComponent):
    '''
    Model class for Cluster Node.
    '''
    meta_type = portal_type = 'MSClusterNode'

    assignedvote = None
    currentvote = None
    state = None
    domain = ""

    _properties = OSComponent._properties + (
        {'id': 'assignedvote', 'label': 'Assigned Vote', 'type': 'string'},
        {'id': 'currentvote', 'label': 'Current Vote', 'type': 'string'},
        {'id': 'state', 'label': 'State', 'type': 'string'},
        {'id': 'domain', 'label': 'Domain', 'type': 'string'},
    )

    _relations = OSComponent._relations + (
        ('os', ToOne(ToManyCont,
         'ZenPacks.zenoss.Microsoft.Windows.OperatingSystem', 'clusternodes')),
        ('clusterdisks', ToManyCont(ToOne,
         'ZenPacks.zenoss.Microsoft.Windows.ClusterDisk', 'clusternode')),
        ('clusterinterfaces', ToManyCont(ToOne,
         'ZenPacks.zenoss.Microsoft.Windows.ClusterInterface', 'clusternode')),
    )

    def ownernodeentity(self):
        deviceRoot = self.dmd.getDmdRoot("Devices")
        try:
            clusterhostip = getHostByName(self.title + "." + self.domain)
            return deviceRoot.findDeviceByIdOrIp(clusterhostip)
        except(gaierror):
            log.warning('Unable to resolve hostname {0}'.format(self.title + "." + self.domain))
            return

    def getRRDTemplateName(self):
        return 'ClusterNode'

    def getIconPath(self):
        '''
        Return the path to an icon for this component.
        '''
        return '/++resource++mswindows/img/server-windows.png'

    def getState(self):
        try:
            state = int(self.cacheRRDValue('state', None))
        except Exception:
            return 'Unknown'

        return cluster_state_string(state)


InitializeClass(ClusterNode)
