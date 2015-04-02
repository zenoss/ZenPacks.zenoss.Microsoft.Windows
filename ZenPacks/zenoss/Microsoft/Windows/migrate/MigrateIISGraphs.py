##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
log = logging.getLogger("zen.migrate")

from Products.ZenModel.ZenPack import ZenPackMigration
from Products.ZenModel.migrate.Migrate import Version

class MigrateIISGraphs(ZenPackMigration):
    ''' Main class that contains the migrate() method.
    Note version setting. '''
    version = Version(2, 4, 0)

    def migrate(self, dmd):
        '''
        This is the main method. It removes the 'IIS - Request Rate graph def.
        '''
        organizer = dmd.Devices.getOrganizer('/Server/Microsoft')
        if organizer:
            self.removeIISGraph(organizer.getRRDTemplates())
            for device in organizer.devices():
                self.removeIISGraph(device.getRRDTemplates())
                
    def removeIISGraph(self, templates):
        for template in templates:
            if 'IIS' in template.id:
                graphs = template.getGraphDefs()
                for graph in graphs:
                    if 'IIS - Request Rate' == graph.id:
                        log.info("Removing 'IIS - Request Rate' graph definition")
                        template.manage_deleteGraphDefinitions((graph.id,))
