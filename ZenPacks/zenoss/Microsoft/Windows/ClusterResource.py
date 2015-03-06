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


class ClusterResource(OSComponent):
    '''
    Model class for Cluster Resources.
    '''
    meta_type = portal_type = 'MSClusterResource'

    ownernode = None
    description = None
    ownergroup = None
    state = None
    domain = ""

    _properties = OSComponent._properties + (
        {'id': 'ownernode', 'label': 'Owner Node', 'type': 'string'},
        {'id': 'description', 'label': 'Description', 'type': 'string'},
        {'id': 'ownergroup', 'label': 'Owner Group', 'type': 'string'},
        {'id': 'state', 'label': 'State', 'type': 'string'},
        {'id': 'domain', 'label': 'Domain', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("clusterservice", ToOne(ToManyCont,
            "ZenPacks.zenoss.Microsoft.Windows.ClusterService",
            "clusterresources")),
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
        return 'ClusterResource'

InitializeClass(ClusterResource)
