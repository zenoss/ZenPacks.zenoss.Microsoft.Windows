##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Globals import InitializeClass

from Products.ZenModel.DeviceComponent import DeviceComponent
from Products.ZenModel.ManagedEntity import ManagedEntity
from Products.ZenRelations.RelSchema import ToOne, ToManyCont, ToMany


class ClusterService(DeviceComponent, ManagedEntity):
    '''
    Model class for Cluster Service.
    '''
    meta_type = portal_type = 'ClusterService'

    ownernode = None
    description = None
    coregroup = False
    priority = 0

    _properties = ManagedEntity._properties + (
        {'id': 'ownernode', 'type': 'string'},
        {'id': 'description', 'type': 'string'},
        {'id': 'coregroup', 'type': 'boolean'},
        {'id': 'priority', 'type': 'integer'},
        )

    _relations = ManagedEntity._relations + (
        ('cluster', ToOne(ToManyCont,
            'ZenPacks.zenoss.Microsoft.Windows.ClusterDevice',
            'clusterservices')),
        ('clusterresources', ToManyCont(ToOne,
            'ZenPacks.zenoss.Microsoft.Windows.ClusterResource',
            'clusterservice')),
    )

    def device(self):
        return self.cluster()

InitializeClass(ClusterService)
