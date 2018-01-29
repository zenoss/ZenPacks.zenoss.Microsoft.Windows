##############################################################################
#
# Copyright (C) Zenoss, Inc. 2018, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version
from Products.Zuul.interfaces import ICatalogTool
from Products.ZenModel.RRDTemplate import RRDTemplate
from Products.AdvancedQuery import Eq
PROGRESS_LOG_INTERVAL = 10

log = logging.getLogger('zen.Microsoft.Windows')

REMOVALS = {
    'MailboxRole': {'datasources': ['msesiRPClatencyAverage'],
                    'graphs': ['RPC Latency Average'],
                    'thresholds': ['rpc_latency_average']},
    'TransportRole': {'datasources': ['msetqActivemailboxDeliveryQueueLength'],
                      'graphs': ['Active mailbox'],
                      'thresholds': ['active_mailbox_delivery_queue_length']}
}


class RemoveExchangeDuplicates(ZenPackMigration):
    # Main class that contains the migrate() method.
    # Note version setting.
    version = Version(2, 8, 4)

    def migrate(self, dmd):
        log.info('Searching for duplicate datasources, graphs, and thresholds to remove from Microsoft Exchange templates.')
        for t, objects in REMOVALS.iteritems():
            results = ICatalogTool(dmd.Devices.Server.Microsoft).search(RRDTemplate, query=Eq('id', t))
            if results.total == 0:
                continue
            for result in results:
                try:
                    template = result.getObject()
                except Exception:
                    continue

                if set(objects['thresholds']).intersection([o.id for o in template.thresholds()]):
                    template.manage_deleteRRDThresholds(objects['thresholds'])
                if set(objects['graphs']).intersection([o.id for o in template.graphDefs()]):
                    template.manage_deleteGraphDefinitions(objects['graphs'])
                if set(objects['datasources']).intersection([o.id for o in template.datasources()]):
                    template.manage_deleteRRDDataSources(objects['datasources'])
