##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
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
from Products.ZenEvents import ZenEventClasses

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

from ZenPacks.zenoss.ZenPackLib import zenpacklib

CFG = zenpacklib.load_yaml([os.path.join(os.path.dirname(__file__), 'zenpack.yaml')])

schema = CFG.zenpack_module.schema


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


def getOSKerberos(osrelease):

    if 'el6' in osrelease:
        return 'kerberos_el6'
    elif 'el5' in osrelease:
        return 'kerberos_el5'
    else:
        return 'kerberos_el6'


class ZenPack(schema.ZenPack):

    binUtilities = ['winrm', 'winrs']

    packZProperties_data = {'zDBInstances': {'type': 'instancecredentials',
                                             'description': 'Microsoft SQL connection parameters',
                                             'label': 'MSSQL Instance parameters'},
                            'zWinRSCodePage': {'type': 'int',
                                               'description': 'Code page used by monitoring user account',
                                               'label': 'Windows Code Page'},
                            'zWinTrustedRealm': {'type': 'string',
                                                 'description': 'Authentication domain trusted by zWinRMUser',
                                                 'label': 'Windows Trusted Realm'},
                            'zWinPerfmonInterval': {'type': 'string', 'description':
                                                    'Interval in seconds at which data is collected',
                                                    'label': 'Windows Collection Interval'},
                            'zWinKeyTabFilePath': {'type': 'string', 'description':
                                                   'Reserved for future use keytab file',
                                                   'label': 'Windows Keytab Path'},
                            'zWinTrustedKDC': {'type': 'string',
                                               'description': 'Domain controller IP or resolvable hostname',
                                               'label': 'Windows Key Distribution Center (Trusted)'},
                            'zWinRMLocale': {'type': 'string',
                                             'description': 'Communication locale to use for monitoring.  Reserved for future use.',
                                             'label': 'Windows Locale'},
                            'zWinRMEnvelopeSize': {'type': 'int',
                                                   'description': 'Used when WinRM configuration setting "MaxEnvelopeSizekb" exceeds default of 512k',
                                                   'label': 'WMI Query Output Envelope Size'},
                            'zWinScheme': {'type': 'string',
                                           'description': 'Either "http" or "https"',
                                           'label': 'Windows Protocol Scheme'},
                            'zWinRMPassword': {'type': 'password', 'description':
                                               'Password for user defined by zWinRMUser',
                                               'label': 'Windows Authentication Password'},
                            'zWinKDC': {'type': 'string',
                                        'description': 'Domain controller IP or resolvable hostname',
                                        'label': 'Windows Key Distribution Center'},
                            'zWinRMPort': {'type': 'string',
                                           'description': 'WS-Management TCP communication port',
                                           'label': 'WS-Management Port'},
                            'zWinRMUser': {'type': 'string',
                                           'description': 'If user@somedomain then zWinKDC and zWinRMServerName are possibly required',
                                           'label': 'Windows Authentication User'},
                            'zWinRMClusterNodeClass': {'type': 'string',
                                                       'description': 'Path under which to create cluster nodes',
                                                       'label': 'Windows Cluster Node Device Class'},
                            'zWinUseWsmanSPN': {'type': 'boolean',
                                                'description': 'Set to true if HTTP/HTTPS service principles are exclusively for use by a particular service account',
                                                'label': 'Use WSMAN Service Principal Name'},
                            'zWinRMKrb5includedir': {'type': 'string',
                                                     'description': 'Directory path for Kerberos config files',
                                                     'label': 'Windows KRB5 Include Directory'},
                            'zWinRMServerName': {'type': 'string',
                                                 'description': 'FQDN for domain authentication if resolution fails or different from AD',
                                                 'label': 'Server Fully Qualified Domain Name'},
                            'zWinRMKrb5DisableRDNS': {'type': 'boolean',
                                                      'description': 'Set to true to disable reverse DNS lookups by kerberos.  Only set at /Server/Microsoft level!',
                                                      'label': 'Disable kerberos reverse DNS'}
                            }

    def install(self, app):
        self.in_install = True
        super(ZenPack, self).install(app)

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

        # updating these manually since ZPL 2.0 doesn't yet support these attributes
        self.update_event_class_mappings(app.zport.dmd)

        self.in_install = False

    def remove(self, app, leaveObjects=False):
        if not leaveObjects:
            self.in_remove = True

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
        self.in_remove = False

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

    def update_event_class_mappings(self, dmd):
        """ZPL 2.0 doesn't support these attributes, so setting them here"""
        # clear classes for each failure type
        clear_class_mappings = {'AuthenticationFailure': ['/Status/Winrm/Auth/instances/AuthenticationSuccess'],
                                'KerberosFailure': ['/Status/Kerberos/instances/KerberosSuccess']
                                }
        for path in ['/Status/Winrm/Auth', '/Status/Kerberos']:
            org = dmd.Events.getOrganizer(path)
            if org:
                for s in ['AuthenticationSuccess', 'KerberosSuccess']:
                    try:
                        success = org.findObject(s)
                        if success:
                            success.setZenProperty('zEventSeverity', ZenEventClasses.Clear)
                    except AttributeError:
                        continue
                for f in ['AuthenticationFailure', 'KerberosFailure']:
                    try:
                        failure = org.findObject(f)
                        if failure:
                            failure.setZenProperty('zEventSeverity', ZenEventClasses.Error)
                            failure.setZenProperty('zEventClearClasses', clear_class_mappings.get(f, []))
                    except AttributeError:
                        continue

# Patch last to avoid import recursion problems.
from ZenPacks.zenoss.Microsoft.Windows import patches  # NOQA: imported for side effects.
