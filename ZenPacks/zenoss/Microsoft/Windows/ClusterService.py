##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Globals import InitializeClass

from Products.ZenModel.OSComponent import OSComponent
from Products.ZenRelations.RelSchema import ToOne, ToManyCont
from Products.ZenUtils.IpUtil import getHostByName


class ClusterService(OSComponent):
    '''
    Model class for Cluster Service.
    '''
    meta_type = portal_type = 'ClusterService'

    ownernode = None
    description = None
    coregroup = False
    priority = 0

    _properties = OSComponent._properties + (
        {'id': 'ownernode', 'type': 'string'},
        {'id': 'description', 'type': 'string'},
        {'id': 'coregroup', 'type': 'boolean'},
        {'id': 'priority', 'type': 'integer'},
        )

    _relations = OSComponent._relations + (
        ('os', ToOne(ToManyCont,
            'ZenPacks.zenoss.Microsoft.Windows.OperatingSystem',
            'clusterservices')),
        ('clusterresources', ToManyCont(ToOne,
            'ZenPacks.zenoss.Microsoft.Windows.ClusterResource',
            'clusterservice')),
    )

    def ownernodeip(self):
        deviceRoot = self.dmd.getDmdRoot("Devices")
        clusterhostip = getHostByName(self.ownernode)
        device = deviceRoot.findDeviceByIdOrIp(clusterhostip)
        return device.getPrimaryUrlPath()

InitializeClass(ClusterService)
