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


class ClusterNetwork(schema.ClusterNetwork):
    '''
    Base class for ClusterNetwork classes.
    
    This file exists to avoid ZenPack upgrade issues
    '''

