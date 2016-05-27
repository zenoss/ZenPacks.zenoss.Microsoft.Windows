##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from . import schema


class WinSQLJob(schema.WinSQLJob):
    '''
    Model class for MSSQLJobs.
    '''

    def monitored(self):
        """Return True if this service should be monitored. False otherwise."""

        return self.monitor and self.enabled == 'Yes'
