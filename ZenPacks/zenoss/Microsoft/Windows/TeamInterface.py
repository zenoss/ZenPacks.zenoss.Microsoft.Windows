##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from . import schema
from zope.event import notify
from Products.Zuul.catalog.events import IndexingEvent
from .utils import get_properties


class TeamInterface(schema.TeamInterface):
    '''
    Model class for TeamInterface.
    '''

    _properties = get_properties(schema.TeamInterface)

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

    def get_niccount(self):
        ''''''
        return len(self.getInterfaces())
