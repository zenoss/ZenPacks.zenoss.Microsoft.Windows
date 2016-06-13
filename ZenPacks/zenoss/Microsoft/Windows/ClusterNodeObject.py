##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from . import schema
from socket import gaierror
from Products.ZenUtils.IpUtil import getHostByName
from utils import cluster_state_string

log = logging.getLogger("zen.MicrosoftWindows")


class ClusterNodeObject(schema.ClusterNodeObject):
    '''
    Base class for Cluster classes.
    '''

    def ownernodeentity(self):
        deviceRoot = self.dmd.getDmdRoot("Devices")
        try:
            clusterhostip = getHostByName(self.ownernode + "." + self.domain)
            return deviceRoot.findDeviceByIdOrIp(clusterhostip)
        except(gaierror):
            log.warning('Unable to resolve hostname {0}'.format(self.title + "." + self.domain))
            return

    def get_host_device(self):
        # first find ownernode or title (if node)
        target = getattr(self, 'ownernode', getattr(self,'title'))
        d = self.device()
        for node in d.os.clusternodes():
            if target != node.title:
                continue
            return node.get_host_device()
        return self.ownernodeentity()

