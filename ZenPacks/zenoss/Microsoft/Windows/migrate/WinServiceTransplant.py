##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""

Reset meta_type and portal_types for objects

"""

# Logging
import logging

# Zenoss Imports
from zope.event import notify
from Products.ZenModel.migrate.Migrate import Version
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.Zuul.catalog.events import IndexingEvent
from Products.Zuul.interfaces import ICatalogTool

# ZenPack Imports
from ZenPacks.zenoss.Microsoft.Windows.WinService import WinService

LOG = logging.getLogger('zen.MicrosoftWindows')


class WinServiceTransplant(ZenPackMigration):
    version = Version(2, 6, 0)

    def migrate(self, pack):
        LOG.info("migrating WinService relations")
        catalog = ICatalogTool(pack.getDmdRoot('Devices'))

        results = catalog.search(WinService)
        if not results.total:
            return

        for result in results:
            try:
                ob = result.getObject()
            except Exception as e:
                continue
            try:
                # transfer object properties from old class
                self.reset_properties(ob)
                # add serviceclass relation
                ob.buildRelations()
                # move object from winrmservices to winservices relation
                self.transplant_service(ob)
                # set the service class
                name = getattr(ob, 'serviceName')
                caption = getattr(ob, 'caption')
                if name and caption:
                    ob.setServiceClass({'name': name, 'description': caption})
                # reindex
                ob.index_object()
                notify(IndexingEvent(ob))
            except Exception as e:
                log.warn('Failed to transplant %s (%s)' % (ob.getDmdKey(), e))

    def reset_properties(self, ob):
        '''set WinService properties'''
        EQUIVALENTS = {'servicename': 'serviceName',
                       'startmode': 'startMode',
                       'account': 'startName',
                       'usermonitor': 'monitor'
                       }
        for old, new in EQUIVALENTS.items():
            val = getattr(ob, old)
            # don't want to set locally to False
            if old == 'usermonitor' and val is False:
                continue
            setattr(ob, new, val)

    def transplant_service(self, ob):
        '''move WinService component to winservices relation from winrmservices'''
        d = ob.device()
        d.os.winservices._add(ob)
        d.os.winrmservices._remove(ob)