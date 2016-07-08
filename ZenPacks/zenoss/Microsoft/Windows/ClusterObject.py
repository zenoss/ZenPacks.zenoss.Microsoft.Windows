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
log = logging.getLogger("zen.MicrosoftWindows")
from socket import gaierror
from Products.ZenUtils.IpUtil import getHostByName
from utils import cluster_state_string


class ClusterObject(schema.ClusterObject):
    '''
    Base class for Cluster classes.
    '''

    def ownernodeentity(self):
        deviceRoot = self.dmd.getDmdRoot("Devices")
        try:
            clusterhostip = getHostByName(self.title + "." + self.domain)
            return deviceRoot.findDeviceByIdOrIp(clusterhostip)
        except(gaierror):
            log.warning('Unable to resolve hostname {0}'.format(self.title + "." + self.domain))
            return

    def getState(self):
        try:
            state = int(self.cacheRRDValue('state', None))
        except Exception:
            return 'Unknown'

        return cluster_state_string(state)


