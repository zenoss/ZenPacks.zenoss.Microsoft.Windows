##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.Zuul.catalog.paths import DefaultPathReporter, relPath


class InterfacePathReporter(DefaultPathReporter):
    def getPaths(self):
        paths = super(InterfacePathReporter, self).getPaths()

        team_interface = self.context.teaminterface()
        if team_interface:
            paths.extend(relPath(team_interface, 'os'))

        return paths
