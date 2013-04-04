##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import os
import base64
import logging
import httplib
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol
from twisted.internet.error import TimeoutError
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from . import response as response_module
from . import contstants as c


class WinrmClient(object):

    def __init__(self, agent, handler, logger):
        self._agent = agent
        self._handler = handler
        self._logger = logger
        self._unauthorized_hosts = []
        self._timedout_hosts = []

    @defer.inlineCallbacks
    def enumerate(self, hostname, username, password, wql, accumulator):
        if hostname in self._unauthorized_hosts:
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(hostname + " previously returned "
                                   "unauthorized. Skipping.")
            return
        if hostname in self._timedout_hosts:
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(hostname + " previously timed out. "
                                   "Skipping.")
            return
        url = "http://{hostname}:5985/wsman".format(hostname=hostname)
        authstr = "{username}:{password}".format(username=username,
                                                 password=password)
        auth = 'Basic ' + base64.encodestring(authstr).strip()
        headers = Headers(
            {'Content-Type': ['application/soap+xml;charset=UTF-8'],
             'Authorization': [auth]})
        request_fmt_filename = get_request_template('enumerate')
        resource_uri_prefix = c.WMICIMV2
        cim_class = wql.split()[-1]
        resource_uri = resource_uri_prefix + '/' + cim_class
        enumeration_context = None
        try:
            while True:
                with open(request_fmt_filename) as f:
                    request_fmt = f.read()
                request = request_fmt.format(
                    resource_uri=resource_uri_prefix + '/*',
                    wql=wql,
                    enumeration_context=enumeration_context)
                if self._logger.isEnabledFor(logging.DEBUG):
                    self._logger.debug(request)
                body = StringProducer(request)
                response = yield self._agent.request('POST', url, headers,
                                                     body)
                if self._logger.isEnabledFor(logging.DEBUG):
                    self._logger.debug("{0} HTTP status: {1}".format(
                        hostname, response.code))
                if response.code == httplib.UNAUTHORIZED:
                    if hostname in self._unauthorized_hosts:
                        return
                    self._unauthorized_hosts.append(hostname)
                    raise Unauthorized("unauthorized, check username and "
                                       "password.")
                if response.code != 200:
                    reader = ErrorReader(hostname, wql, self._logger)
                    response.deliverBody(reader)
                    yield reader.d
                    raise Exception("HTTP status" + str(response.code))
                enumeration_context = yield self._handler.handle_response(
                    response, resource_uri, cim_class, accumulator)
                if not enumeration_context:
                    break
                request_fmt_filename = get_request_template('pull')
        except TimeoutError, e:
            if hostname in self._timedout_hosts:
                return
            self._timedout_hosts.append(hostname)
            self._logger.error('{0} {1}'.format(hostname, e))
            raise
        except Exception, e:
            self._logger.error('{0} {1}'.format(hostname, e))
            raise


class WinrmClientFactory(object):

    def __init__(self, logger):
        self._logger = logger

    def _create_agent(self):
        try:
            # HTTPConnectionPool has been present since Twisted version 12.1
            from twisted.web.client import HTTPConnectionPool
            pool = HTTPConnectionPool(reactor, persistent=True)
            pool.maxPersistentPerHost = c.MAX_PERSISTENT_PER_HOST
            pool.cachedConnectionTimeout = c.CACHED_CONNECTION_TIMEOUT
            return Agent(reactor, connectTimeout=c.CONNECT_TIMEOUT, pool=pool)
        except ImportError:
            return Agent(reactor)

    def _create_response_handler(self, xml_parser):
        if xml_parser == 'etree':
            return response_module.ElementTreeResponseHandler(self._logger)
        if xml_parser == 'cetree':
            return response_module.cElementTreeResponseHandler(self._logger)
        if xml_parser != 'sax' and self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug('Unknown XML parser "' + xml_parser
                               + '", using SAX parser')
        return response_module.ExpatResponseHandler(self._logger)

    def create_winrm_client(self, xml_parser='sax'):
        agent = self._create_agent()
        handler = self._create_response_handler(xml_parser)
        return WinrmClient(agent, handler, self._logger)


class ErrorReader(Protocol):

    def __init__(self, hostname, wql, logger):
        self.d = defer.Deferred()
        self._hostname = hostname
        self._wql = wql
        self._logger = logger
        self._data = ""

    def dataReceived(self, data):
        self._data += data

    def connectionLost(self, reason):
        from xml.etree import ElementTree
        tree = ElementTree.fromstring(self._data)
        self._logger.error("{0._hostname} --> {0._wql}".format(self))
        self._logger.error(tree.findtext("Envelope/Body/Fault/Reason/Text"))
        self._logger.error(tree.findtext(
            "Envelope/Body/Fault/Detail/MSFT_WmiError/Message"))
        self.d.callback(None)


class StringProducer(object):

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)


class Unauthorized(Exception):
    pass


def get_request_template(name):
    basedir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(basedir, 'request', name + '.xml')
