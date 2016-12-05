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


class WinSQLDatabase(schema.WinSQLDatabase):
    '''
    Base class for WinSQLDatabase classes.

    This file exists to avoid ZenPack upgrade issues
    '''
    def getStatus(self):
        try:
            status = int(self.cacheRRDValue('status', None))
        except Exception:
            return 'Unknown'

        return 'Up' if status else 'Down'
