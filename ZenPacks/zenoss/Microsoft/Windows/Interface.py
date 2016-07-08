##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from . import schema
from .utils import get_properties


class Interface(schema.Interface):
    '''
    Model class for Interface
    '''
    portal_type = meta_type = 'IpInterface'

    _properties = get_properties(schema.Interface)

    def monitored(self):
        '''
        Return the monitored status of this component.

        Overridden from IpInterface to prevent monitoring
        administratively down interfaces.
        '''
        return self.monitor and self.adminStatus == 1

