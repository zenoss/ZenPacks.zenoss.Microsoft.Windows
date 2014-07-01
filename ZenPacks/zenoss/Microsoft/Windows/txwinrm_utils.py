##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import re

from .utils import addLocalLibPath
addLocalLibPath()

# Requires that addLocalLibPath be called above.
from txwinrm.collect import ConnectionInfo
from txwinrm.util import UnauthorizedError


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

    if int(device_proxy.zWinRMPort) == 5985 and scheme == 'https':
        raise UnauthorizedError("zWinRMPort must be 5986 if zWinScheme is https")

    if int(device_proxy.zWinRMPort) == 5986 and scheme == 'http':
        raise UnauthorizedError("zWinRMPort must be 5985 if zWinScheme is http")

    return ConnectionInfo(
        hostname=hostname,
        auth_type=auth_type,
        username=username,
        password=password,
        scheme=device_proxy.zWinScheme,
        port=int(device_proxy.zWinRMPort),
        connectiontype='Keep-Alive',
        keytab=device_proxy.zWinKeyTabFilePath,
        dcip=device_proxy.zWinKDC)
