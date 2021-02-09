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

    @property
    def is_availability_database(self):
        """
        Define whether Database is Always On protected or not.
        For this purpose check Always On Unique ID.
        :return: Boolean
        """
        # Check Always On Unique ID.
        if self.unigue_id and \
                self.unigue_id not in ('n/a', 'None'):
            return True
        return False

    def getRRDTemplates(self):
        if self.is_availability_database:
            template_name = 'WinAODatabase'
        else:
            template_name = 'WinDatabase'

        rrd_templates = super(WinSQLDatabase, self).getRRDTemplates()
        if rrd_templates:
            for tempalte in rrd_templates:
                if tempalte.id == template_name:
                    return [tempalte]

        return []
