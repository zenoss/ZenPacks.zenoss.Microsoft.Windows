##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
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
import logging

from Products.ZenUtils.Utils import zenPath

try:
    from ZenPacks.zenoss.Impact.impactd.relations import ImpactEdge, DSVRelationshipProvider, RelationshipEdgeError
    from ZenPacks.zenoss.Impact.impactd.interfaces import IRelationshipDataProvider
except ImportError:
    IMPACT_INSTALLED = False
else:
    IMPACT_INSTALLED = True

log = logging.getLogger("zen.MicrosoftWindows")
# unused
Globals

ZENPACK_NAME = 'ZenPacks.zenoss.Microsoft.Windows'

DEVTYPE_NAME = 'Windows Server'
DEVTYPE_PROTOCOL = 'WinRM'
OLD_DEVTYPE_PROTOCOL = 'WMI'


from . import zenpacklib

# CFG is necessary when using zenpacklib.TestCase.
CFG = zenpacklib.load_yaml()

from . import schema


# Used by zenchkschema to validate relationship schema.
productNames = (
    'ClusterDevice',
    'ClusterResource',
    'ClusterService',
    'ClusterNode',
    'ClusterDisk',
    'ClusterNetwork',
    'ClusterInterface',
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

EXCH_WARN = 'Impact definitions have changed in this version of the ZenPack.'\
    '  You must update to the latest version of the Exchange Server ZenPack.'
SEGFAULT_INFO = "If a Segmentation fault occurs, then run the installation "\
    "once more.  This is a known issue that only occurs when upgrading from v2.1.3 or older."


def getOSKerberos(osrelease):

    if 'el6' in osrelease:
        return 'kerberos_el6'
    elif 'el5' in osrelease:
        return 'kerberos_el5'
    else:
        return 'kerberos_el6'


class ZenPack(schema.ZenPack):

    binUtilities = ['winrm', 'winrs']

    def install(self, app):
        super(ZenPack, self).install(app)

        self.register_devtype(app.zport.dmd)
        log.info(SEGFAULT_INFO)

        try:
            exchange_version = self.dmd.ZenPackManager.packs._getOb(
                'ZenPacks.zenoss.Microsoft.Exchange').version
            if IMPACT_INSTALLED and \
               exchange_version in ('1.0.0', '1.0.1', '1.0.2'):
                log.warn(EXCH_WARN)
        except AttributeError:
            pass

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

        self.cleanup_zProps(app.zport.dmd)

    def remove(self, app, leaveObjects=False):
        if not leaveObjects:
            self.unregister_devtype(app.zport.dmd)

            # remove kerberos.so file from python path
            kerbdst = os.path.join(zenPath('lib', 'python'), 'kerberos.so')
            kerbconfig = os.path.join(os.environ['ZENHOME'], 'var', 'krb5')
            userenvironconfig = '{0}/.bashrc'.format(os.environ['HOME'])

            try:
                os.remove(kerbdst)
                # Remove directory, if it exists.
                shutil.rmtree(kerbconfig, ignore_errors=True)
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
            old_deviceclass.unregister_devtype(DEVTYPE_NAME, OLD_DEVTYPE_PROTOCOL)

        deviceclass = dmd.Devices.createOrganizer('/Server/Microsoft/Windows')
        deviceclass.register_devtype(DEVTYPE_NAME, DEVTYPE_PROTOCOL)

    def unregister_devtype(self, dmd):
        '''
        Unregister the "Windows Server (WinRM)" devtype.
        '''
        try:
            deviceclass = dmd.Devices.Microsoft.Windows
        except AttributeError:
            # Someone removed the device class. That's fine.
            return

        deviceclass.unregister_devtype(DEVTYPE_NAME, DEVTYPE_PROTOCOL)

    def cleanup_zProps(self, dmd):
        # Delete zProperty when updating the older zenpack version without reinstall.
        devices = dmd.Devices
        try:
            devices.deleteZenProperty('zDBInstancesPassword')
        except Exception:
            pass
        # workaround for ZEN-13662
        devices._properties = tuple(
            [x for x in devices._properties if x['id'] != 'zDBInstancesPassword']
        )


# Patch last to avoid import recursion problems.
from ZenPacks.zenoss.Microsoft.Windows import patches  # NOQA: imported for side effects.
