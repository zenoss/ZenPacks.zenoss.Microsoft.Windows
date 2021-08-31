##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import re
import logging

from .utils import addLocalLibPath
addLocalLibPath()

# Requires that addLocalLibPath be called above.
from txwinrm.collect import ConnectionInfo
from txwinrm.util import UnauthorizedError

log = logging.getLogger("zen.MicrosoftWindows")

# Tuple of DeviceProxy properties required by createConnectionInfo.
ConnectionInfoProperties = (
    'windows_user',
    'windows_password',
    'windows_servername',
    'zWinRMPort',
    'zWinKDC',
    'zWinKeyTabFilePath',
    'zWinScheme',
    'zDBInstances',
    'zWinTrustedRealm',
    'zWinTrustedKDC',
    'zWinUseWsmanSPN',
    'zWinRMEnvelopeSize',
    'zWinRMLocale',
    'zWinRMEncoding',
    'zWinRSCodePage',
    'zWinRMKrb5includedir',
    'zWinRMKRBErrorThreshold',
    'kerberos_rdns',
    'zWinRMConnectTimeout',
    'zWinRMLongRunningCommandOperationTimeout',
    'zWinRMConnectionCloseTime',
    'zSQLAlwaysOnEnabled',
    'zWinServicesModeled',
    'zWinServicesNotModeled',
    'snmpSysName',
)


def createConnectionInfo(device_proxy):
    """Return a ConnectionInfo given device proxy.

    UnauthorizedError exception will be raised if the credentials are
    found to be invalid.

    """
    if not hasattr(device_proxy, 'windows_servername'):
        raise UnauthorizedError(
            "attempted Windows connection to non-Windows device")

    hostname = device_proxy.windows_servername or device_proxy.manageIp

    username = device_proxy.windows_user
    if not username:
        raise UnauthorizedError("zWinRMUser or zWinUser must be configured")

    # Warn about old-style usernames of the DOMAIN\User format.
    pattern = r'[a-zA-Z0-9][a-zA-Z0-9.]{0,14}\\[^"/\\\[\]:;|=,+*?<>]{1,104}'
    if re.match(pattern, username):
        raise UnauthorizedError(
            "zWinRMUser must be user@example.com, not DOMAIN\User")

    password = device_proxy.windows_password
    if not password:
        raise UnauthorizedError(
            "zWinRMPassword or zWinPassword must be configured")

    auth_type = 'kerberos' if '@' in username else 'basic'
    if auth_type == 'kerberos' and not device_proxy.zWinKDC:
        raise UnauthorizedError(
            "zWinKDC must be configured for domain authentication")

    scheme = device_proxy.zWinScheme.lower()
    if scheme not in ('http', 'https'):
        raise UnauthorizedError(
            "zWinScheme must be either 'http' or 'https'")

    ok_ports = (5986, 443)
    if int(device_proxy.zWinRMPort) not in ok_ports and scheme == 'https':
        raise UnauthorizedError("zWinRMPort must be 5986 or 443 if zWinScheme is https")

    ok_ports = (5985, 80)
    if int(device_proxy.zWinRMPort) not in ok_ports and scheme == 'http':
        raise UnauthorizedError("zWinRMPort must be 5985 or 80 if zWinScheme is http")

    trusted_realm = trusted_kdc = ''
    if hasattr(device_proxy, 'zWinTrustedRealm') and hasattr(device_proxy, 'zWinTrustedKDC'):
        trusted_realm = device_proxy.zWinTrustedRealm
        trusted_kdc = device_proxy.zWinTrustedKDC
        if device_proxy.zWinTrustedRealm and not device_proxy.zWinTrustedKDC or\
           not device_proxy.zWinTrustedRealm and device_proxy.zWinTrustedKDC:
            log.debug('zWinTrustedKDC and zWinTrustedRealm must both be populated in order to add a trusted realm.')

    service = scheme
    if hasattr(device_proxy, 'zWinUseWsmanSPN') and device_proxy.zWinUseWsmanSPN:
        service = 'wsman'

    def getWinAttr(device, name, default):
        value = getattr(device, name, default) if device else default
        # If property exists on object but not defined, return default instead
        return value if value != None else default

    envelope_size = getWinAttr(device_proxy, 'zWinRMEnvelopeSize', 512000)
    locale = getWinAttr(device_proxy, 'zWinRMLocale', 'en-US')
    code_page = getWinAttr(device_proxy, 'zWinRSCodePage', 65001)

    include_dir = getWinAttr(device_proxy, 'zWinRMKrb5includedir', None)
    disable_rdns = getWinAttr(device_proxy, 'kerberos_rdns', False)

    connect_timeout = getWinAttr(device_proxy, 'zWinRMConnectTimeout', 60)
    connection_close_time = getWinAttr(device_proxy, 'zWinRMConnectionCloseTime', 60)

    timeout = getWinAttr(device_proxy, 'zWinRMConnectTimeout', 60)

    return ConnectionInfo(
        hostname=hostname,
        auth_type=auth_type,
        username=username,
        password=password,
        scheme=device_proxy.zWinScheme,
        port=int(device_proxy.zWinRMPort),
        connectiontype='Keep-Alive',
        keytab=device_proxy.zWinKeyTabFilePath,
        dcip=device_proxy.zWinKDC,
        timeout=timeout,
        trusted_realm=trusted_realm,
        trusted_kdc=trusted_kdc,
        ipaddress=device_proxy.manageIp,
        service=service,
        envelope_size=envelope_size,
        locale=locale,
        code_page=code_page,
        include_dir=include_dir,
        disable_rdns=disable_rdns,
        connect_timeout=connect_timeout,
        connection_close_time=connection_close_time
    )


def modify_connection_info(connection_info, datasource_config, data_to_reset=None):

    if not isinstance(connection_info, ConnectionInfo):
        log.debug('Provided Connection info %s is not with proper type %s, cant modify',
                  connection_info,
                  type(connection_info))
        return connection_info

    # Availability Replica performance counters are placed on other nodes unlike other counters.
    # Need to pick up right Windows node for this type of counters.
    replica_perfdata_node = getattr(datasource_config, 'replica_perfdata_node', None)
    replica_perfdata_node_ip = datasource_config.params['replica_perfdata_node_ip']
    if replica_perfdata_node and replica_perfdata_node_ip:
        connection_info = connection_info._replace(hostname=replica_perfdata_node)
        connection_info = connection_info._replace(ipaddress=replica_perfdata_node_ip)
    # allow for collection from sql clusters where active sql instance
    # could be running on different node from current host server
    # ex. sol-win03.solutions-wincluster.loc//SQL1 for MSSQLSERVER
    # sol-win03.solutions-wincluster.loc//SQL3\TESTINSTANCE1
    #       for TESTINSTANCE1
    # standalone ex.
    #       //SQLHOSTNAME for MSSQLSERVER
    #       //SQLTEST\TESTINSTANCE1 for TESTINSTANCE1
    elif getattr(datasource_config, 'cluster_node_server', None) and \
            datasource_config.params['owner_node_ip']:
        owner_node, server = \
            datasource_config.cluster_node_server.split('//')
        if owner_node:
            connection_info = connection_info._replace(hostname=owner_node)
            connection_info = connection_info._replace(
                ipaddress=datasource_config.params['owner_node_ip'])

    # Set fields which were provided additionally
    if isinstance(data_to_reset, dict):
        connection_info = connection_info._replace(**data_to_reset)

    return connection_info
