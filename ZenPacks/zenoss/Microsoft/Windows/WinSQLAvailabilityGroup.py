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

    def get_sql_instance(self):
        """
        Returns SQL Instance on which Availability Groups' Primary Replica is placed.
        """
        sql_instance = None

        winsqlinstance_relation = getattr(self, 'winsqlinstance')
        if winsqlinstance_relation:
            sql_instance = winsqlinstance_relation()

        return sql_instance

    @property
    def cluster_node_server(self):
        hosted_sql_instance = self.get_sql_instance()
        if hosted_sql_instance:
            return getattr(hosted_sql_instance, 'cluster_node_server', '')

    @property
    def perfmon_instance(self):
        hosted_sql_instance = self.get_sql_instance()
        if hosted_sql_instance:
            return getattr(hosted_sql_instance, 'perfmon_instance', '')

    @property
    def owner_node_ip(self):
        hosted_sql_instance = self.get_sql_instance()
        if hosted_sql_instance:
            return getattr(hosted_sql_instance, 'owner_node_ip', '')

    @property
    def instancename(self):
        hosted_sql_instance = self.get_sql_instance()
        if hosted_sql_instance:
            return getattr(hosted_sql_instance, 'instancename', '')
