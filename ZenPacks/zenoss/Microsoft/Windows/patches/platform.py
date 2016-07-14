##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import twisted.web.client
import twisted.web.http

from Products.ZenModel.OSProcess import OSProcess
from Products.ZenUtils.Utils import monkeypatch


if not hasattr(OSProcess, 'getMinProcessCount'):
    @monkeypatch(OSProcess)
    def getMinProcessCount(self):
        return None

if not hasattr(OSProcess, 'getMaxProcessCount'):
    @monkeypatch(OSProcess)
    def getMaxProcessCount(self):
        return None


if hasattr(twisted.web.client, '_AgentBase'):
    @monkeypatch(twisted.web.client._AgentBase)
    def _computeHostValue(self, scheme, host, port):
        """
        Compute the string to use for the value of the I{Host} header, based on
        the given scheme, host name, and port number.

        Monkeypatched by ZenPacks.zenoss.Microsoft.Windows to be tolerant of IPv6
        host addresses.
        """
        if ':' in host:
            # HTTP host header must be surrounded by brackets if it's an IPv6
            # address literal.
            host = '[{}]'.format(host)

        return original(self, scheme, host, port)  # NOQA: original injected


if hasattr(twisted.web.client, '_URI'):
    @classmethod
    def fromBytes(cls, uri, defaultPort=None):
        """
        Parse the given URI into a L{_URI}.

        Monkeypatched by ZenPacks.zenoss.Microsoft.Windows to be tolerant of IPv6
        host addresses.

        @type uri: C{bytes}
        @param uri: URI to parse.

        @type defaultPort: C{int} or C{None}
        @param defaultPort: An alternate value to use as the port if the URI
            does not include one.

        @rtype: L{_URI}
        @return: Parsed URI instance.
        """
        uri = uri.strip()
        scheme, netloc, path, params, query, fragment = twisted.web.http.urlparse(uri)

        if defaultPort is None:
            if scheme == b'https':
                defaultPort = 443
            else:
                defaultPort = 80

        host, port = netloc, defaultPort
        if b':' in host:
            # This is the only line changed from the original method. It had been
            # the following, which resulted in an unpacking error on IPv6 addresses
            # because they can contain many colons.
            #
            #     host, port = host.split(b':')
            host, port = host.rsplit(b':', 1)
            try:
                port = int(port)
            except ValueError:
                port = defaultPort

        return cls(scheme, netloc, host, port, path, params, query, fragment)

    # Must monkeypatch by hand because it's a classmethod.
    twisted.web.client._URI.fromBytes = fromBytes


@monkeypatch('Products.Zuul.facades.devicefacade.DeviceFacade')
def getDevTypes(self, uid):
    """
    The purpose of this patch is to filter out legacy /Server/Microsoft device class
    from 'Add infrastructure' page of quick setup wizard (ZEN-20431).
    """
    data = original(self, uid)
    if not uid == '/zport/dmd/Devices/Server':
        return data
    return filter(lambda x: x['value'] != '/zport/dmd/Devices/Server/Microsoft',
                  data)

@monkeypatch('Products.Zuul.facades.templatefacade.TemplateFacade')
def _editDetails(self, info, data):
    """
    Calls `post_update` method if defined.
    """
    result = original(self, info, data)

    if hasattr(info, 'post_update'):
        info.post_update()

    return result
