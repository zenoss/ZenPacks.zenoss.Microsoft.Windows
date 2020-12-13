##############################################################################
#
# Copyright (C) Zenoss, Inc. 2020, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema


class WinSQLAvailabilityGroup(schema.WinSQLAvailabilityGroup):
    '''
    Base class for WinSQLAvailabilityGroup classes.

    This file exists to avoid ZenPack upgrade issues
    '''

    def getStatus(self):
        return super(WinSQLAvailabilityGroup, self).getStatus('/')
