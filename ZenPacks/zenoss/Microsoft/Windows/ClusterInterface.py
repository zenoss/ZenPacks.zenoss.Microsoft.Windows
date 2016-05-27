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


class ClusterInterface(schema.ClusterInterface):
    '''
    Base class for Cluster classes.
    '''

    def get_network(self):
        ''''''
        networks = self.device().os.clusternetworks()
        for network in networks:
            if network.title == self.network:
                return network
        return None

    def get_host_device(self):
        ''''''
        deviceRoot = self.dmd.getDmdRoot("Devices")
        return deviceRoot.findDeviceByIdOrIp(self.ipaddresses)
