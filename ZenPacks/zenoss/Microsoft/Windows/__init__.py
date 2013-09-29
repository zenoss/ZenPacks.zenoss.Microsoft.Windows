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

# unused
Globals

DEVTYPE_NAME = 'Windows Server'
DEVTYPE_PROTOCOL = 'WMI'

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

    def install(self, app):
        super(ZenPack, self).install(app)

        self.register_devtype(app.zport.dmd)

        # add symlinks for command line utilities
        for utilname in self.binUtilities:
            self.installBinFile(utilname)

    def remove(self, app, leaveObjects=False):
        if not leaveObjects:
            self.unregister_devtype(app.zport.dmd)

            # remove symlinks for command line utilities
            for utilname in self.binUtilities:
                self.removeBinFile(utilname)

        super(ZenPack, self).remove(app, leaveObjects=leaveObjects)

    def register_devtype(self, dmd):
        '''
        Register or replace the "Windows Server (WMI)" devtype.
        '''
        try:
            old_deviceclass = dmd.Devices.Server.Windows.WMI
        except AttributeError:
            # No old device class. That's fine.
            pass
        else:
            old_deviceclass.unregister_devtype(DEVTYPE_NAME, DEVTYPE_PROTOCOL)

        deviceclass = dmd.Devices.createOrganizer('/Server/Microsoft/Windows')
        deviceclass.register_devtype(DEVTYPE_NAME, DEVTYPE_PROTOCOL)

    def unregister_devtype(self, dmd):
        '''
        Unregister the "Windows Server (WMI)" devtype.
        '''
        try:
            deviceclass = dmd.Devices.Microsoft.Windows
        except AttributeError:
            # Someone removed the device class. That's fine.
            return

        deviceclass.unregister_devtype(DEVTYPE_NAME, DEVTYPE_PROTOCOL)
