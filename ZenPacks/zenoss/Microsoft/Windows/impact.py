##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

try:
    from ZenPacks.zenoss.Impact.impactd.relations import ImpactEdge, DSVRelationshipProvider, RelationshipEdgeError
    from ZenPacks.zenoss.Impact.impactd.interfaces import IRelationshipDataProvider
except ImportError:
    IMPACT_INSTALLED = False
else:
    IMPACT_INSTALLED = True


if IMPACT_INSTALLED:
    from ZenPacks.zenoss.Microsoft.Windows.zenpacklib import ImpactRelationshipDataProvider

    class DeviceRelationsProvider(ImpactRelationshipDataProvider):
        '''RelationsProvider stub for backwards compatibility'''
