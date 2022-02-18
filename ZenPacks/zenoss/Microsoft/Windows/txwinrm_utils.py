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
    'zWinRMUser',
    'zWinRMPassword',
    'zWinRMServerName',
)


def createConnectionInfo(device_proxy):
    """Return a ConnectionInfo given device proxy.

    UnauthorizedError exception will be raised if the credentials are
    found to be invalid.

    """
    def getProxyValue(props):
        if not isinstance(props, list):
            props = [props]
        for p in props:
            if hasattr(device_proxy, p):
                attr = getattr(device_proxy, p)
                val = attr() if callable(attr) else attr
                if val:
                    return val
        return ""

    hostname = getProxyValue(['windows_servername', 'zWinRMServerName', 'manageIp'])
    if not hostname:
        raise UnauthorizedError("Attempted Windows connection to non-Windows device")

    username = getProxyValue(['windows_user', 'zWinRMUser', 'zWinUser'])
    if not username:
        raise UnauthorizedError(
            "Cannot connect to Windows with an unknown user, zWinRMUser or zWinUser must be configured")

    # Warn about old-style usernames of the DOMAIN\User format.
    if re.match(r'[a-zA-Z0-9][a-zA-Z0-9.]{0,14}\\[^"/\\\[\]:;|=,+*?<>]{1,104}', username):
        raise UnauthorizedError("zWinRMUser must be user@example.com, not DOMAIN\User")

    password = getProxyValue(['windows_password', 'zWinRMPassword'])
    if not password:
        raise UnauthorizedError("zWinRMPassword or zWinPassword must be configured")

    winKDC = getProxyValue(['zWinKDC', 'zWinTrustedKDC'])
    auth_type = 'kerberos' if '@' in username else 'basic'
    if auth_type == 'kerberos' and not winKDC:
        raise UnauthorizedError("zWinKDC must be configured for domain authentication")

    scheme = getProxyValue('zWinScheme')
    scheme = scheme if hasattr(scheme, 'lower') else ''
    if scheme not in ('http', 'https'):
        raise UnauthorizedError("zWinScheme must be either 'http' or 'https'")

    try:
        port = int(getProxyValue('zWinRMPort'))
        if port not in (5986, 443) and scheme == 'https':
            raise Exception()
        if port not in (5985, 80) and scheme == 'http':
            raise Exception()
    except Exception:
        raise UnauthorizedError("zWinRMPort must be 5986 or 443 if zWinScheme is https")

    trusted_realm = getProxyValue('zWinTrustedRealm')
    trusted_kdc = getProxyValue('zWinTrustedKDC')
    if trusted_realm and not trusted_kdc or not trusted_realm and trusted_kdc:
        log.debug('zWinTrustedKDC and zWinTrustedRealm must both be populated in order to add a trusted realm.')

    useSPN = getProxyValue('zWinUseWsmanSPN')
    service = 'wsman' if useSPN else scheme

    keyTab = getProxyValue('zWinKeyTabFilePath')
    manageIp = getProxyValue('manageIp')

    def getWinAttr(device, name, default):
        value = getattr(device, name, default) if device else default
        # If property exists on object but not defined, return default instead
        return value if value != None else default

    envelope_size         = getWinAttr(device_proxy, 'zWinRMEnvelopeSize', 512000)
    locale                = getWinAttr(device_proxy, 'zWinRMLocale', 'en-US')
    code_page             = getWinAttr(device_proxy, 'zWinRSCodePage', 65001)
    include_dir           = getWinAttr(device_proxy, 'zWinRMKrb5includedir', None)
    disable_rdns          = getWinAttr(device_proxy, 'kerberos_rdns', False)
    connect_timeout       = getWinAttr(device_proxy, 'zWinRMConnectTimeout', 60)
    connection_close_time = getWinAttr(device_proxy, 'zWinRMConnectionCloseTime', 60)
    timeout               = getWinAttr(device_proxy, 'zWinRMConnectTimeout', 60)

    return ConnectionInfo(
        hostname=hostname,
        auth_type=auth_type,
        username=username,
        password=password,
        scheme=scheme,
        port=port,
        connectiontype='Keep-Alive',
        keytab=keyTab,
        dcip=winKDC,
        timeout=timeout,
        trusted_realm=trusted_realm,
        trusted_kdc=trusted_kdc,
        ipaddress=manageIp,
        service=service,
        envelope_size=envelope_size,
        locale=locale,
        code_page=code_page,
        include_dir=include_dir,
        disable_rdns=disable_rdns,
        connect_timeout=connect_timeout,
        connection_close_time=connection_close_time,
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
