##############################################################################
#
# Copyright (C) Zenoss, Inc. 2020, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema
from .utils import lookup_ag_state


class WinSQLAvailabilityGroup(schema.WinSQLAvailabilityGroup):

    def getState(self):
        try:
            state = int(self.cacheRRDValue('AvailabilityGroupState_IsOnline', 0))
        except (ValueError, Exception):
            state = None

        status_representation = lookup_ag_state(state)

        return status_representation
