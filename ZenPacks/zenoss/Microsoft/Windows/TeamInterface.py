##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


from Globals import InitializeClass

from zope.event import notify

from Products.AdvancedQuery import Eq

from Products.ZenModel.OSComponent import OSComponent
from Products.ZenModel.IpInterface import IpInterface
from Products.ZenRelations.RelSchema import ToManyCont, ToMany, ToOne
from Products.Zuul.catalog.events import IndexingEvent
from Products.Zuul.interfaces import ICatalogTool


def interface_by_id(device, interface_id):
    catalog = ICatalogTool(device.primaryAq())

    search_results = catalog.search(
        query=Eq('id', interface_id))

    for result in search_results.results:
        return result.getObject()


class TeamInterface(IpInterface, OSComponent):
    meta_type = portal_type = 'WinTeamInterface'

    _relations = OSComponent._relations + (
        ('os', ToOne(ToManyCont,
            'ZenPacks.zenoss.Microsoft.Windows.OperatingSystem',
            'teaminterfaces')),
        ('ipaddresses', ToMany(ToOne,
            'Products.ZenModel.IpAddress',
            'interface')),
        ('iproutes', ToMany(ToOne,
            'Products.ZenModel.IpRouteEntry',
            'interface')),
        ('teaminterfaces', ToMany(ToOne,
            'ZenPacks.zenoss.Microsoft.Windows.Interface',
            'teaminterface')),
        )

    def setInterfaces(self, ids):
        new_ids = set(ids)
        current_ids = set(x.id for x in self.teaminterfaces())
        for id_ in new_ids.symmetric_difference(current_ids):
            interface = interface_by_id(self.device(), id_)

            if interface:
                if id_ in new_ids:
                    self.teaminterfaces.addRelation(interface)
                else:
                    self.teaminterfaces.removeRelation(interface)

                notify(IndexingEvent(interface, 'path', False))

    def getInterfaces(self):
        return sorted([x.id for x in self.teaminterfaces()])

InitializeClass(TeamInterface)
