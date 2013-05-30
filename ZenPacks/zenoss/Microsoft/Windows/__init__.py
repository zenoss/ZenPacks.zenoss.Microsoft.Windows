##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

__doc__ = "Microsoft Windows ZenPack"

import Globals
from Products.ZenModel.ZenPack import ZenPackBase

# unused
Globals


class ZenPack(ZenPackBase):

    binUtilities = ['genkrb5conf', 'typeperf', 'wecutil', 'winrm', 'winrs']

    def install(self, *args):
        super(ZenPack, self).install(*args)

        # add symlinks for command line utilities
        for utilname in self.binUtilities:
            self.installBinFile(utilname)

    def remove(self, *args):
        super(ZenPack, self).remove(*args)

        # remove symlinks for command line utilities
        for utilname in self.binUtilities:
            self.removeBinFile(utilname)
