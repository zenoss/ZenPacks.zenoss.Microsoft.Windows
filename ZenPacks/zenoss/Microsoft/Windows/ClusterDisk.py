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


class ClusterDisk(OSComponent):
    '''
    Model class for Cluster Disks.
    '''
    meta_type = portal_type = 'MSClusterDisk'

    volumepath = None
    ownernode = None
    disknumber = None
    partitionnumber = None
    size = None
    freespace = None
    assignedto = None
    state = None
    domain = ""

    _properties = OSComponent._properties + (
        {'id': 'volumepath', 'label': 'Volume Path', 'type': 'string'},
        {'id': 'ownernode', 'label': 'Owner Node', 'type': 'string'},
        {'id': 'disknumber', 'label': 'Disk Number', 'type': 'string'},
        {'id': 'partitionnumber', 'label': 'Partition Number', 'type': 'string'},
        {'id': 'size', 'label': 'Size', 'type': 'string'},
        {'id': 'freespace', 'label': 'Free Space', 'type': 'string'},
        {'id': 'state', 'label': 'State', 'type': 'string'},
        {'id': 'assignedto', 'label': 'Assigned To', 'type': 'string'},
        {'id': 'domain', 'label': 'Domain', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("clusternode", ToOne(ToManyCont,
            "ZenPacks.zenoss.Microsoft.Windows.ClusterNode",
            "clusterdisks")),
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
        return 'ClusterDisk'

    def getIconPath(self):
        '''
        Return the path to an icon for this component.
        '''
        return '/++resource++mswindows/img/FileSystem.png'

    def getState(self):
        try:
            state = int(self.cacheRRDValue('state', None))
        except Exception:
            return 'Unknown'

        return cluster_state_string(state)

InitializeClass(ClusterDisk)
