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


class ClusterNode(schema.ClusterNode):
    '''
    Base class for ClusterNode classes.
    '''

    def get_network(self):
        ''''''
        return None

    def get_host_device(self):
        ''''''
        for interface in self.clusterinterfaces():
            d = interface.get_host_device()
            if d:
                return d
        return None
