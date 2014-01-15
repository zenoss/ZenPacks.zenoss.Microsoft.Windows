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
import platform
import shutil
import re

from Products.ZenModel.ZenPack import ZenPackBase
from Products.ZenRelations.zPropertyCategory import setzPropertyCategory
from Products.ZenUtils.Utils import monkeypatch, zenPath

# unused
Globals

ZENPACK_NAME = 'ZenPacks.zenoss.Microsoft.Windows'

DEVTYPE_NAME = 'Windows Server'
DEVTYPE_PROTOCOL = 'WMI'


_PACK_Z_PROPS = [
    ('zWinRMUser', '', 'string'),
    ('zWinRMPassword', '', 'password'),
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


def getOSKerberos(osrelease):

    if 'el6' in osrelease:
        return 'kerberos_el6'
    elif 'el5' in osrelease:
        return 'kerberos_el5'
    else:
        return 'kerberos_el6'


class ZenPack(ZenPackBase):

    binUtilities = ['winrm', 'winrs']
    packZProperties = _PACK_Z_PROPS

    def install(self, app):
        super(ZenPack, self).install(app)

        self.register_devtype(app.zport.dmd)

        # copy kerberos.so file to python path
        osrelease = platform.release()
        kerbsrc = os.path.join(os.path.dirname(__file__), 'lib', getOSKerberos(osrelease), 'kerberos.so')

        kerbdst = zenPath('lib', 'python')
        shutil.copy(kerbsrc, kerbdst)

        # Set KRB5_CONFIG environment variable
        userenvironconfig = '{0}/.bashrc'.format(os.environ['HOME'])
        if 'KRB5_CONFIG' not in open(userenvironconfig).read():
            environmentfile = open(userenvironconfig, "a")
            environmentfile.write('# Following value required for Windows ZenPack\n')
            environmentfile.write('export KRB5_CONFIG="{0}/var/krb5/krb5.conf"\n'.format(
                os.environ['ZENHOME']))
            environmentfile.close()

        # add symlinks for command line utilities
        for utilname in self.binUtilities:
            self.installBinFile(utilname)

    def remove(self, app, leaveObjects=False):
        if not leaveObjects:
            self.unregister_devtype(app.zport.dmd)

            # remove kerberos.so file from python path
            kerbdst = os.path.join(zenPath('lib', 'python'), 'kerberos.so')
            kerbconfig = os.path.join(os.environ['ZENHOME'], 'var', 'krb5')
            userenvironconfig = '{0}/.bashrc'.format(os.environ['HOME'])

            try:
                os.remove(kerbdst)
                os.remove(kerbconfig)
                # Remove export for KRB5_CONFIG from bashrc
                bashfile = open(userenvironconfig, 'r')
                content = bashfile.read()
                bashfile.close()
                content = re.sub(r'# Following value required for Windows ZenPack\n?',
                    '',
                    content)
                content = re.sub(r'export KRB5_CONFIG.*\n?', '', content)
                newbashfile = open(userenvironconfig, 'w')
                newbashfile.write(content)
                newbashfile.close()

            except Exception:
                pass

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


from Products.ZenModel.OSProcess import OSProcess
if not hasattr(OSProcess, 'getMinProcessCount'):
    @monkeypatch("Products.ZenModel.OSProcess.OSProcess")
    def getMinProcessCount(self):
        return None

if not hasattr(OSProcess, 'getMaxProcessCount'):
    @monkeypatch("Products.ZenModel.OSProcess.OSProcess")
    def getMaxProcessCount(self):
        return None
