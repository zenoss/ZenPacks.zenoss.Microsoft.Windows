##############################################################################
#
# Copyright (C) Zenoss, Inc. 2020, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema


class WinSQLAvailabilityGroupHostedObject(schema.WinSQLAvailabilityGroupHostedObject):
    """
    Base class for components, which are hosted on MSSQL Always On Availability Group.
    """

    def get_availability_group(self):
        ag = None

        winsqlavailabilitygroup_relation = getattr(self, 'winsqlavailabilitygroup', None)
        if winsqlavailabilitygroup_relation:
            ag = winsqlavailabilitygroup_relation()

        return ag

    @property
    def availability_group_name(self):
        ag_name = ''

        availability_group = self.get_availability_group()
        if availability_group:
            ag_name = availability_group.name()

        return ag_name
