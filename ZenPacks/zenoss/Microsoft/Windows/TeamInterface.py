##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


from zope.event import notify

from Products.ZenModel.IpInterface import IpInterface
from Products.ZenRelations.RelSchema import ToMany, ToOne
from Products.Zuul.catalog.events import IndexingEvent


class TeamInterface(IpInterface):
    meta_type = portal_type = 'WinTeamInterface'

    _relations = IpInterface._relations + (
        ('teaminterfaces', ToMany(ToOne,
            'ZenPacks.zenoss.Microsoft.Windows.Interface',
            'teaminterface')),
        )

    def monitored(self):
        '''
        Return the monitored status of this component.

        Overridden from IpInterface to prevent monitoring
        administratively down interfaces.
        '''
        return self.monitor and self.adminStatus == 1

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

            # For componentSearch. Would be nice if we could target
            # idxs=['getAllPaths'], but there's a chance that it won't
            # exist yet.
            interface.index_object()

    def getInterfaces(self):
        return sorted([x.id for x in self.teaminterfaces()])
