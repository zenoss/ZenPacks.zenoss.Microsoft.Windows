##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema
from utils import cluster_disk_state_string


class ClusterDisk(schema.ClusterDisk):
    '''
    class for Cluster Disk.
    '''

    def getState(self):
        status = 'None'
        try:
            state = int(self.cacheRRDValue('state', None))
            status = cluster_disk_state_string(state)
        except Exception:
            status = 'Error Encountered'

        return status

