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
import os
import shutil

from Products.ZenModel.ZenPack import ZenPackBase
from Products.ZenRelations.zPropertyCategory import setzPropertyCategory
from Products.ZenUtils.Utils import monkeypatch, unused, zenPath

# unused
Globals

ZENPACK_NAME = 'ZenPacks.zenoss.Microsoft.Windows'

DEVTYPE_NAME = 'Windows Server'
DEVTYPE_PROTOCOL = 'WMI'


_PACK_Z_PROPS = [
    ('zWinUser', '', 'string'),
    ('zWinPassword', '', 'password'),
    ('zWinRMPort', '5985', 'string'),
    ('zDBInstances', 'MSSQLSERVER;', 'string'),
    ('zDBInstancesPassword', '', 'password'),
    ('zWinKDC', '', 'string'),
    ('zWinKeyTabFilePath', '', 'string'),
    ('zWinScheme', 'http', 'string'),
    ('zWinPerfmonInterval', 300, 'int'),
    ]

for name, default_value, type_ in _PACK_Z_PROPS:
    setzPropertyCategory(name, 'Windows')

# General zProp for Instance logins
# Format example:
# zDBInstanceLogin = 'MSSQLSERVER;ZenossInstance2'
# zDBInstnacePassword = 'sa:Pzwrd;sa:i24ns3'


setzPropertyCategory('zDBInstances', 'Misc')
setzPropertyCategory('zDBInstancesPassword', 'Misc')

# zProperties we share with WindowsMonitor. Require special handling.
SHARED_ZPROPERTIES = ('zWinUser', 'zWinPassword')

# Used by zenchkschema to validate relationship schema.
productNames = (
    'ClusterDevice',
    'ClusterResource',
    'ClusterService',
    'CPU',
    'Device',
    'Interface',
    'OperatingSystem',
    'OSProcess',
    'TeamInterface',
    'WinIIS',
    'WinService',
    'WinSQLBackup',
    'WinSQLDatabase',
    'WinSQLInstance',
    'WinSQLJob',
    )


class ZenPack(ZenPackBase):

    binUtilities = ['genkrb5conf', 'typeperf', 'wecutil', 'winrm', 'winrs']
    packZProperties = _PACK_Z_PROPS

    def install(self, app):
        super(ZenPack, self).install(app)

        self.usurp_zproperties(app.zport.dmd)
        self.register_devtype(app.zport.dmd)

        #copy kerberos.so file to python path
        kerbsrc = os.path.join(os.path.dirname(__file__), 'lib', 'kerberos.so')
        kerbdst = zenPath('lib', 'python')
        shutil.copy(kerbsrc, kerbdst)

        # add symlinks for command line utilities
        for utilname in self.binUtilities:
            self.installBinFile(utilname)

    def remove(self, app, leaveObjects=False):
        if not leaveObjects:
            self.unregister_devtype(app.zport.dmd)
            self.cede_zproperties(app.zport.dmd)

            # remove kerberos.so file from python path
            kerbdst = os.path.join(zenPath('lib', 'python'), 'kerberos.so')
            kerbconfig = os.path.join(os.environ['ZENHOME'], 'var', 'krb5')

            try:
                os.remove(kerbdst)
                os.remove(kerbconfig)
            except Exception:
                pass

            # remove symlinks for command line utilities
            for utilname in self.binUtilities:
                self.removeBinFile(utilname)

        super(ZenPack, self).remove(app, leaveObjects=leaveObjects)

    def usurp_zproperties(self, dmd):
        '''
        Usurp control of zProperties from the WindowsMonitor ZenPack.

        This is done to prevent WindowsMonitor from removing zProperties
        this ZenPack adds and needs when WindowsMonitor is removed.
        '''
        try:
            old = dmd.getObjByPath(
                'ZenPackManager/packs/ZenPacks.zenoss.WindowsMonitor')
        except Exception:
            return

        old.packZProperties = [
            t for t in old.packZProperties if t[0] not in SHARED_ZPROPERTIES]

    def cede_zproperties(self, dmd):
        '''
        In the event that this ZenPack is removed from a system that
        still has WindowsMonitor installed, cede control of shared
        zProperties back to WindowsMonitor.
        '''
        try:
            old = dmd.getObjByPath(
                'ZenPackManager/packs/ZenPacks.zenoss.WindowsMonitor')

            # Fall back to class definition instead of instance.
            del(old.packZProperties)
        except Exception:
            return

        # Prevent removal of shared properties.
        self.packZProperties = [
            t for t in self.packZProperties if t[0] not in SHARED_ZPROPERTIES]

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


from Products.ZenModel.OSProcess import OSProcess
if not hasattr(OSProcess, 'getMinProcessCount'):
    @monkeypatch("Products.ZenModel.OSProcess.OSProcess")
    def getMinProcessCount(self):
        return None

if not hasattr(OSProcess, 'getMaxProcessCount'):
    @monkeypatch("Products.ZenModel.OSProcess.OSProcess")
    def getMaxProcessCount(self):
        return None


# Patch last to avoid import recursion problems.
from ZenPacks.zenoss.Microsoft.Windows import patches
unused(patches)
