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


class ClusterResource(OSComponent):
    '''
    Model class for Cluster Resources.
    '''
    meta_type = portal_type = 'ClusterResource'

    ownernode = None
    description = None
    ownergroup = None
    state = None

    _properties = OSComponent._properties + (
        {'id': 'ownernode', 'type': 'string'},
        {'id': 'description', 'type': 'string'},
        {'id': 'ownergroup', 'type': 'string'},
        {'id': 'state', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("clusterservice", ToOne(ToManyCont,
            "ZenPacks.zenoss.Microsoft.Windows.ClusterService",
            "clusterresources")),
    )

    def ownernodeip(self):
        deviceRoot = self.dmd.getDmdRoot("Devices")
        clusterhostip = getHostByName(self.ownernode)
        device = deviceRoot.findDeviceByIdOrIp(clusterhostip)
        return device.getPrimaryUrlPath()


InitializeClass(ClusterResource)
