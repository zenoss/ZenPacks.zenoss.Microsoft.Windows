##############################################################################
#
# Copyright (C) Zenoss, Inc. 2020, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema


class WinSQLInstanceHostedObject(schema.WinSQLInstanceHostedObject):
    """
    Base class for components, which are hosted on SQL Instance.
    """

    def get_sql_instance(self):
        """
        Returns SQL Instance on which Availability Replicas' Primary Replica is placed. TODO: revise this
        """
        sql_instance = None

        winsqlinstance_relation = getattr(self, 'winsqlinstance', None)
        if winsqlinstance_relation:
            sql_instance = winsqlinstance_relation()

        return sql_instance

    @property
    def cluster_node_server(self):
        hosted_sql_instance = self.get_sql_instance()
        if hosted_sql_instance:
            return getattr(hosted_sql_instance, 'cluster_node_server', '')
        return ''

    @property
    def perfmon_instance(self):
        hosted_sql_instance = self.get_sql_instance()
        if hosted_sql_instance:
            return getattr(hosted_sql_instance, 'perfmon_instance', '')
        return ''

    @property
    def owner_node_ip(self):
        hosted_sql_instance = self.get_sql_instance()
        if hosted_sql_instance:
            return getattr(hosted_sql_instance, 'owner_node_ip', '')
        return ''

    @property
    def instancename(self):
        hosted_sql_instance = self.get_sql_instance()
        if hosted_sql_instance:
            return getattr(hosted_sql_instance, 'instancename', '')
        return ''
