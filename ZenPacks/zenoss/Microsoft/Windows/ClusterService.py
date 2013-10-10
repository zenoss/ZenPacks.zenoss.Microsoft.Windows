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

log = logging.getLogger("zen.MicrosoftWindows")
from Products.ZenModel.OSComponent import OSComponent
from Products.ZenRelations.RelSchema import ToOne, ToManyCont
from Products.ZenUtils.IpUtil import getHostByName


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

    _properties = OSComponent._properties + (
        {'id': 'ownernode', 'type': 'string'},
        {'id': 'description', 'type': 'string'},
        {'id': 'coregroup', 'type': 'boolean'},
        {'id': 'priority', 'type': 'integer'},
        {'id': 'state', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ('os', ToOne(ToManyCont,
            'ZenPacks.zenoss.Microsoft.Windows.OperatingSystem',
            'clusterservices')),
        ('clusterresources', ToManyCont(ToOne,
            'ZenPacks.zenoss.Microsoft.Windows.ClusterResource',
            'clusterservice')),
    )

    def ownernodeurl(self):
        deviceRoot = self.dmd.getDmdRoot("Devices")
        try:
            clusterhostip = getHostByName(self.ownernode)
            device = deviceRoot.findDeviceByIdOrIp(clusterhostip)
            return device.getPrimaryUrlPath()
        except(gaierror):
            log.warning('Unable to resolve hostname {0}'.format(self.ownernode))
            return

    def getRRDTemplateName(self):
        return 'ClusterService'

InitializeClass(ClusterService)
