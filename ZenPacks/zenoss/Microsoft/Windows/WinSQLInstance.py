##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema


class WinSQLInstance(schema.WinSQLInstance):
    '''
    Base class for WinSQLDatabase classes.

    This file exists to avoid ZenPack upgrade issues
    '''

    def getStatus(self):
        return super(WinSQLInstance, self).getStatus('/')
