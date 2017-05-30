##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema
from utils import get_rrd_path

class Interface(schema.Interface):
    '''
    Model class for Interface
    '''
    portal_type = meta_type = 'IpInterface'

    # preserve the old style path
    rrdPath = get_rrd_path

    def monitored(self):
        '''
        Return the monitored status of this component.

        Overridden from IpInterface to prevent monitoring
        administratively down interfaces.
        '''
        return self.monitor and self.adminStatus == 1
