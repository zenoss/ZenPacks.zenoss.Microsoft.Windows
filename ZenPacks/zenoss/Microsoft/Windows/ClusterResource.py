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
from Products.ZenRelations.RelSchema import ToOne, ToManyCont


class ClusterResource(DeviceComponent, ManagedEntity):
    '''
    Model class for Cluster Resources.
    '''
    meta_type = portal_type = 'ClusterResource'

    ownernode = None
    description = None
    ownergroup = None
    state = None

    _properties = ManagedEntity._properties + (
        {'id': 'ownernode', 'type': 'string'},
        {'id': 'description', 'type': 'string'},
        {'id': 'ownergroup', 'type': 'string'},
        {'id': 'state', 'type': 'string'},
        )

    _relations = ManagedEntity._relations + (
        ('clusterservice', ToOne(ToManyCont,
            'ZenPacks.zenoss.Microsoft.Windows.ClusterService',
            'clusterresources')),
    )

    def device(self):
        return self.clusterservice().cluster()

InitializeClass(ClusterResource)
