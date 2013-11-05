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

from Products.ZenModel.OSComponent import OSComponent
from Products.ZenModel.IpInterface import IpInterface
from Products.ZenRelations.RelSchema import ToManyCont, ToMany, ToOne
from Products.Zuul.catalog.events import IndexingEvent


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
            interface = self.device().os.interfaces._getOb(id_, None)

            if interface:
                if id_ in new_ids:
                    self.teaminterfaces.addRelation(interface)
                else:
                    self.teaminterfaces.removeRelation(interface)

                notify(IndexingEvent(interface, 'path', False))

    def getInterfaces(self):
        return sorted([x.id for x in self.teaminterfaces()])

InitializeClass(TeamInterface)
