##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Use twisted web client to enumerate/pull WQL query.
"""

import os
import base64

from twisted.web.http_headers import Headers
from twisted.internet import  defer

import contstants as const


def get_request_template(name):
    basedir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(basedir, 'request', name + '.xml')


class StringProducer(object):

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)


class WinrmClient(object):

    def __init__(self, username, password, hostname):

        self._authstr = "{username}:{password}".format(username=username,
                                                 password=password)
        self._auth = 'Basic ' + base64.encodestring(self._authstr).strip()
        self._url = "http://{hostname}:5985/wsman".format(hostname=hostname)
        self._headers = Headers(
            {'Content-Type': ['application/soap+xml;charset=UTF-8'],
             'Authorization': [self._auth]})
        self._requestTemplate = get_request_template('enumerate')
        self._uri_prefix = const.WMICIMV2

    def enumerate(self, wql):
        cim_class = wql.split()[-1]

        resource_uri = self._uri_prefix + '/' + cim_class

        enumeration_context = None

        enum_template_file = open(self._requestTemplate)

        enum_template = enum_template_file.read()
        request = enum_template.format(
                    resource_uri=resource_uri + '/*',
                    wql=wql,
                    enumeration_context=enumeration_context)

        body = StringProducer(request)

        return {'url': self._url,
                'headers': self._headers,
                'body': body}
