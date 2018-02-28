##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017-2018, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema
from utils import cluster_disk_state_string, sizeof_fmt


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

    def getSize(self):
        if self.size == -1:
            return 'N/A'
        return sizeof_fmt(self.size)
