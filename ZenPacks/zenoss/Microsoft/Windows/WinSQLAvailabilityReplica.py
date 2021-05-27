##############################################################################
#
# Copyright (C) Zenoss, Inc. 2021, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema


class WinSQLAvailabilityReplica(object, schema.WinSQLAvailabilityReplica):

    @property
    def replica_perfdata_node(self):
        """
        Availability Replica performance counter object imposes a limitation that Replica-hosting Windows node do not
        have performance data about that particular Availability Replica. To be able to collect these performance
        counters, we need to specify separate replica Windows host instead.

        Availability Group Primary replica hostname have all information about all AGs replicas, except replica on
        the node. Secondary Replica nodes have the information about AG Primary Replica.
        """
        result = ''

        def local_node():
            return ''

        def separate_node():
            perfdata_node = ''

            # Get Availability Group of this Availability replica
            ag = self.get_availability_group()
            if not ag:
                return perfdata_node

            # Get first Availability Group's Availability replicas which is not current Replica
            availability_replicas = None
            availability_replicas_relation = getattr(ag, 'winsqlavailabilityreplicas', None)
            if availability_replicas_relation:
                availability_replicas = availability_replicas_relation()
                if not availability_replicas:
                    return perfdata_node
            perfdata_replica = None
            if availability_replicas:
                for ar in availability_replicas:
                    # Node must be separate, as there is no counters about replica itself on hosting node.
                    # Primary replica node has info about the rest of replicas (but not about itself).
                    if ar.id != self.id\
                            and ar.role != self.role:
                        perfdata_replica = ar
                        break
            if not perfdata_replica:
                return perfdata_node

            # Get Availability replica's Windows node
            sql_instance_fullname = getattr(perfdata_replica, 'cluster_node_server', '')
            fullname_parts = sql_instance_fullname.split('//')
            if len(fullname_parts) == 2:
                ar_owner_node = fullname_parts[0]
                if ar_owner_node:
                    perfdata_node = ar_owner_node

            return perfdata_node

        node_location_mapping = {
            'local': local_node,
            'separate': separate_node,
            'default': separate_node
        }

        node_location = None
        if self.hasProperty('zSQLAlwaysOnReplicaPerfdataNode', useAcquisition=True):
            node_location = self.getProperty('zSQLAlwaysOnReplicaPerfdataNode')
        if node_location:
            node_location_func = node_location_mapping.get(node_location.strip())
            if node_location_func:
                result = node_location_func()

        if not result:
            result = node_location_mapping.get('default')()

        return result

    def get_replica_perfdata_node_ip(self):
        node_ip = ''

        node = self.replica_perfdata_node
        if node:
            try:
                node_ip = self.device().clusterhostdevicesdict.get(node)
            except Exception as e:
                pass

        return node_ip
