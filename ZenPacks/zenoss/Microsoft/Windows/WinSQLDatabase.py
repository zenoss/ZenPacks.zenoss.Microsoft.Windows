##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from . import schema
from utils import get_rrd_path, DB_STATUSES


class WinSQLDatabase(schema.WinSQLDatabase):
    """
    Base class for WinSQLDatabase classes.

    """
    rrdPath = get_rrd_path

    def getDBStatus(self):
        """Return database state"""
        dbstatus = 'Unknown'
        if not self.monitored():
            return dbstatus

        dbstatus = ''
        try:
            # use a bitmask to determine all statuses for the database
            status_value = int(self.cacheRRDValue('status', None))
            for key, status in DB_STATUSES.iteritems():
                if key & status_value != 0:
                    if dbstatus:
                        dbstatus += ', '
                    dbstatus += status
        except Exception:
            dbstatus = 'Unknown'
        return dbstatus

    def monitored(self):
        instance = getattr(self, 'winsqlinstance', None)
        if instance and not instance().monitored():
            return False
        return self.monitor
