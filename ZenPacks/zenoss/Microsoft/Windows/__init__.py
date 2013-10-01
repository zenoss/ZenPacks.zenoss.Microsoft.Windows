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
from Products.ZenRelations.zPropertyCategory import setzPropertyCategory
from Products.ZenUtils.Utils import monkeypatch

# unused
Globals

ZENPACK_NAME = 'ZenPacks.zenoss.Microsoft.Windows'

_PACK_Z_PROPS = [('zWinUser', '', 'string'),
                ('zWinPassword', '', 'password'),
                ('zWinRMPort', '5985', 'string'),
                ('zDBInstances', 'MSSQLSERVER;', 'string'),
                ('zDBInstancesPassword', '', 'password')]

for name, default_value, type_ in _PACK_Z_PROPS:
    setzPropertyCategory(name, 'Windows')

# General zProp for Instance logins
# Format example:
# zDBInstanceLogin = 'MSSQLSERVER;ZenossInstance2'
# zDBInstnacePassword = 'sa:Pzwrd;sa:i24ns3'


setzPropertyCategory('zDBInstances', 'Misc')
setzPropertyCategory('zDBInstancesPassword', 'Misc')


class ZenPack(ZenPackBase):

    binUtilities = ['genkrb5conf', 'typeperf', 'wecutil', 'winrm', 'winrs']
    packZProperties = _PACK_Z_PROPS

    def install(self, *app):
        super(ZenPack, self).install(*app)

        # add symlinks for command line utilities
        for utilname in self.binUtilities:
            self.installBinFile(utilname)

    def remove(self, *app):
        # remove symlinks for command line utilities
        for utilname in self.binUtilities:
            self.removeBinFile(utilname)


from Products.ZenModel.OSProcess import OSProcess
if not hasattr(OSProcess, 'getMinProcessCount'):
    @monkeypatch("Products.ZenModel.OSProcess.OSProcess")
    def getMinProcessCount(self):
        return None

if not hasattr(OSProcess, 'getMaxProcessCount'):
    @monkeypatch("Products.ZenModel.OSProcess.OSProcess")
    def getMaxProcessCount(self):
        return None
