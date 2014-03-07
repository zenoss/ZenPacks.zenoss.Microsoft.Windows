######################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is
# installed.
#
######################################################################


from zope.component import adapts
from zope.interface import implements

from Products.ZenRelations.ToManyRelationship import ToManyRelationshipBase
from Products.ZenRelations.ToOneRelationship import ToOneRelationship
from Products.ZenUtils.guid.interfaces import IGlobalIdentifier

from ZenPacks.zenoss.Impact.impactd import Trigger
from ZenPacks.zenoss.Impact.impactd.relations import ImpactEdge
from ZenPacks.zenoss.Impact.impactd.interfaces import IRelationshipDataProvider
from ZenPacks.zenoss.Impact.impactd.interfaces import INodeTriggers

AVAILABILITY = 'AVAILABILITY'
PERCENT = 'policyPercentageTrigger'
THRESHOLD = 'policyThresholdTrigger'
RP = 'ZenPacks.zenoss.Microsoft.Windows'


def guid(obj):
    return IGlobalIdentifier(obj).getGUID()


def edge(source, target):
    return ImpactEdge(source, target, RP)


def getRedundancyTriggers(guid, format, **kwargs):
    """Return a general redundancy set of triggers."""

    return (
        Trigger(guid, format % 'DOWN', PERCENT, AVAILABILITY, dict(
            kwargs, state='DOWN', dependentState='DOWN', threshold='100',
        )),
        Trigger(guid, format % 'DEGRADED', THRESHOLD, AVAILABILITY, dict(
            kwargs, state='DEGRADED', dependentState='DEGRADED', threshold='1',
        )),
        Trigger(guid, format % 'ATRISK_1', THRESHOLD, AVAILABILITY, dict(
            kwargs, state='ATRISK', dependentState='DOWN', threshold='1',
        )),
        Trigger(guid, format % 'ATRISK_2', THRESHOLD, AVAILABILITY, dict(
            kwargs, state='ATRISK', dependentState='ATRISK', threshold='1',
        )),
    )


def getPoolTriggers(guid, format, **kwargs):
    """Return a general pool set of triggers."""

    return (
        Trigger(guid, format % 'DOWN', PERCENT, AVAILABILITY, dict(
            kwargs, state='DOWN', dependentState='DOWN', threshold='100',
        )),
        Trigger(guid, format % 'DEGRADED', THRESHOLD, AVAILABILITY, dict(
            kwargs, state='DEGRADED', dependentState='DEGRADED', threshold='1',
        )),
        Trigger(guid, format % 'ATRISK_1', THRESHOLD, AVAILABILITY, dict(
            kwargs, state='DEGRADED', dependentState='DOWN', threshold='1',
        )),
    )


class BaseRelationsProvider(object):
    implements(IRelationshipDataProvider)

    relationship_provider = RP
    impact_relationships = None
    impacted_by_relationships = None

    def __init__(self, adapted):
        self._object = adapted

    def belongsInImpactGraph(self):
        return True

    def guid(self):
        if not hasattr(self, '_guid'):
            self._guid = guid(self._object)

        return self._guid

    def impact(self, relname):
        relationship = getattr(self._object, relname, None)
        if relationship:
            if isinstance(relationship, ToOneRelationship):
                obj = relationship()
                if obj:
                    yield edge(self.guid(), guid(obj))

            elif isinstance(relationship, ToManyRelationshipBase):
                for obj in relationship():
                    yield edge(self.guid(), guid(obj))

    def impacted_by(self, relname):
        relationship = getattr(self._object, relname, None)
        if relationship:
            if isinstance(relationship, ToOneRelationship):
                obj = relationship()
                if obj:
                    yield edge(guid(obj), self.guid())

            elif isinstance(relationship, ToManyRelationshipBase):
                for obj in relationship():
                    yield edge(guid(obj), self.guid())

    def getEdges(self):
        if self.impact_relationships is not None:
            for impact_relationship in self.impact_relationships:
                for impact in self.impact(impact_relationship):
                    yield impact

        if self.impacted_by_relationships is not None:
            for impacted_by_relationship in self.impacted_by_relationships:
                for impacted_by in self.impacted_by(impacted_by_relationship):
                    yield impacted_by


class BaseTriggers(object):
    implements(INodeTriggers)

    def __init__(self, adapted):
        self._object = adapted


# ----------------------------------------------------------------------------
# Impact relationships

class DeviceRelationsProvider(BaseRelationsProvider):
    impacted_by_relationships = []
    impact_relationships = []

    def getEdges(self):
        for impact in super(DeviceRelationsProvider, self).getEdges():
            yield impact

        # File Systems
        for obj in self._object.os.filesystems():
            yield edge(guid(obj), self.guid())

        # Processors
        for obj in self._object.hw.cpus():
            yield edge(guid(obj), self.guid())

        # Interfaces
        for obj in self._object.os.interfaces():
            yield edge(guid(obj), self.guid())

        # IIS Sites
        for obj in self._object.os.winrmiis():
            yield edge(guid(obj), self.guid())

        # DB Instances
        for obj in self._object.os.winsqlinstances():
            yield edge(guid(obj), self.guid())

        # Cluster Services
        for obj in self._object.os.clusterservices():
            yield edge(guid(obj), self.guid())

        # Look up for HyperV server with same IP
        try:
            dc = self._object.getDmdRoot('Devices').getOrganizer('/Server/Microsoft/HyperV')
        except Exception:
            return

        results = ICatalogTool(dc).search()

        for brain in results:
            obj = brain.getObject()
            if hasattr(obj, 'ip'):
                if obj.ip == self._object.id:
                    yield edge(self.guid(), guid(obj))


class FileSystemRelationsProvider(BaseRelationsProvider):

    def getEdges(self):
        yield edge(self.guid(), guid(self.device()))


class CPURelationsProvider(BaseRelationsProvider):

    def getEdges(self):
        yield edge(self.guid(), guid(self.device()))


class InterfaceRelationsProvider(BaseRelationsProvider):

    def getEdges(self):
        yield edge(self.guid(), guid(self.device()))


class IISRelationsProvider(BaseRelationsProvider):

    def getEdges(self):
        yield edge(self.guid(), guid(self.device()))


class SQLRelationsProvider(BaseRelationsProvider):

    def getEdges(self):
        yield edge(self.guid(), guid(self.device()))


class ClusterRelationsProvider(BaseRelationsProvider):

    def getEdges(self):
        yield edge(self.guid(), guid(self.device()))
