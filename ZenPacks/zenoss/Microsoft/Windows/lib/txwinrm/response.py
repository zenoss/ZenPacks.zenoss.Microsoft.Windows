##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""WinRM response handlers.

Choices for XML parsers of SOAP responses from WinRM services:

    cElementTree.iterparse
        clearing elements as they are processed
        synchronous but fast

    ElementTree.XMLParser
        asynchronous using feed method

    sax.expatreader.ExpatParser
        asynchronous using feed method
"""

import logging
from collections import deque
from cStringIO import StringIO

from xml.etree import cElementTree
from xml.etree import ElementTree
from xml import sax

from twisted.internet import defer
from twisted.internet.protocol import Protocol
from twisted.web._newclient import ResponseFailed

from . import contstants as c


class EnumerationContextTracker(object):

    def __init__(self):
        self._enumeration_context = None
        self._end_of_sequence = False

    @property
    def enumeration_context(self):
        if not self._end_of_sequence:
            return self._enumeration_context

    def append_element(self, uri, localname, text):
        if uri == c.XML_NS_ENUMERATION:
            if localname == c.WSENUM_ENUMERATION_CONTEXT:
                self._enumeration_context = text
            elif localname == c.WSENUM_END_OF_SEQUENCE:
                self._end_of_sequence = True


class TagComparer(object):

    def __init__(self, uri, localname):
        self._uri = uri.lower()
        self._localname = localname.lower()

    def matches(self, uri, localname):
        return self._uri == uri.lower() \
            and self._localname == localname.lower()


class EtreeEventHandler(object):
    """Used by ElementTree and cElementTree parsing"""

    def __init__(self, root, accumulator, resource_uri, cim_class):
        self._root = root
        self._accumulator = accumulator
        self._resource_uri = resource_uri
        self._cim_class = cim_class
        self._tracker = EnumerationContextTracker()
        self._in_items = False

    def handle_event(self, event, elem):
        if '}' in elem.tag:
            uri, localname = elem.tag.split('}')
        else:
            uri = ''
            localname = elem.tag
        uri = uri[1:]
        tag = TagComparer(uri, localname)
        if tag.matches(c.XML_NS_WS_MAN, c.WSENUM_ITEMS) \
                or tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_ITEMS):
            self._in_items = event == 'start'
        elif not self._in_items:
            self._tracker.append_element(uri, localname, elem.text)
        else:
            if (tag.matches(self._resource_uri, self._cim_class)
                    or tag.matches(c.XML_NS_WS_MAN, c.WSM_XML_FRAGMENT)):
                if event == "start":
                    self._accumulator.new_instance()
            elif event == "end":
                self._accumulator.append_element(uri, localname, elem.text)
        if event == "end":
            self._root.clear()

    @property
    def enumeration_context(self):
        return self._tracker.enumeration_context


class AsyncParseReader(Protocol):
    """Used by ElementTree and expat parsing"""

    def __init__(self, xml_parser, logger, finished_func=None):
        self._xml_parser = xml_parser
        self._logger = logger
        self._finished = finished_func
        if finished_func is None:
            self._finished = xml_parser.finished
        self._debug_data = ''

    def dataReceived(self, data):
        if self._logger.isEnabledFor(logging.DEBUG):
            self._debug_data += data
        self._xml_parser.feed(data)

    def connectionLost(self, reason):
        if self._logger.isEnabledFor(logging.DEBUG):
            import xml.dom.minidom
            xml = xml.dom.minidom.parseString(self._debug_data)
            self._logger.debug(xml.toprettyxml())
        if isinstance(reason.value, ResponseFailed):
            self._logger.error("Connection lost: {0}".format(
                reason.value.reasons[0]))
        self._finished()


# cElementTree parsing --------------------------------------------------------

class StringIOReader(Protocol):

    def __init__(self, logger):
        self._logger = logger
        self.deferred_string_io = defer.Deferred()
        self._string_io = StringIO()

    def dataReceived(self, data):
        self._string_io.write(data)

    def connectionLost(self, reason):
        if isinstance(reason.value, ResponseFailed):
            self._logger.error("Connection lost: {0}".format(
                reason.value.reasons[0]))
        self._string_io.reset()
        self.deferred_string_io.callback(self._string_io)


class cElementTreeResponseHandler(object):

    def __init__(self, logger):
        self._logger = logger

    @defer.inlineCallbacks
    def handle_response(self, response, resource_uri, cim_class, accumulator):
        reader = StringIOReader(self._logger)
        response.deliverBody(reader)
        source = yield reader.deferred_string_io
        context = cElementTree.iterparse(source, events=("start", "end"))
        context = iter(context)
        event, root = context.next()
        handler = EtreeEventHandler(root, accumulator, resource_uri, cim_class)
        for event, elem in context:
            handler.handle_event(event, elem)
        defer.returnValue(handler.enumeration_context)


# ElementTree parsing ---------------------------------------------------------

class WsmanElementTreeParser(ElementTree.XMLParser):

    def __init__(self, html=0, target=None, encoding=None):
        ElementTree.XMLParser.__init__(self, html, target, encoding)
        self._handle_event_backlog = deque()
        self._get_event_backlog = deque()

    def get_event(self):
        if self._handle_event_backlog:
            return self._handle_event_backlog.popleft()
        d = defer.Deferred()
        self._get_event_backlog.append(d)
        return d

    def finished(self):
        self._handle_event(None, None)

    def _start_list(self, tag, attrib_in):
        """callback from ElementTree.XMLParser"""
        elem = ElementTree.XMLParser._start_list(self, tag, attrib_in)
        self._handle_event("start", elem)

    def _end(self, tag):
        """callback from ElementTree.XMLParser"""
        elem = ElementTree.XMLParser._end(self, tag)
        self._handle_event("end", elem)

    def _handle_event(self, event, elem):
        if self._get_event_backlog:
            d = self._get_event_backlog.popleft()
            d.callback((event, elem))
            return
        d = defer.Deferred()
        d.callback((event, elem))
        self._handle_event_backlog.append(d)


class ElementTreeResponseHandler(object):

    def __init__(self, logger):
        self._logger = logger

    @defer.inlineCallbacks
    def handle_response(self, response, resource_uri, cim_class, accumulator):
        parser = WsmanElementTreeParser()
        reader = AsyncParseReader(parser, self._logger)
        response.deliverBody(reader)
        start_event, root = yield parser.get_event()
        handler = EtreeEventHandler(root, accumulator, resource_uri, cim_class)
        while True:
            event, elem = yield parser.get_event()
            if event is None:
                break
            handler.handle_event(event, elem)
        defer.returnValue(handler.enumeration_context)


# sax expat parsing -----------------------------------------------------------

class WsmanSaxContentHandler(sax.handler.ContentHandler):

    def __init__(self, accumulator, resource_uri, cim_class):
        self._accumulator = accumulator
        self._resource_uri = resource_uri
        self._cim_class = cim_class
        self._tracker = EnumerationContextTracker()
        self._buffer = StringIO()
        self._in_items = False

    @property
    def enumeration_context(self):
        return self._tracker.enumeration_context

    def startElementNS(self, name, qname, attrs):
        self._element('start', name)

    def endElementNS(self, name, qname):
        text = self._buffer.getvalue()
        text = None if not text else text
        self._buffer.reset()
        self._buffer.truncate()
        uri, localname, tag = self._element('end', name)
        if localname is None:
            return
        if self._in_items:
            self._accumulator.append_element(uri, localname, text)
        else:
            self._tracker.append_element(uri, localname, text)

    def characters(self, content):
        self._buffer.write(content)

    def _element(self, event, name):
        uri, localname = name
        if uri is None:
            uri = ''
        tag = TagComparer(uri, localname)
        if tag.matches(c.XML_NS_WS_MAN, c.WSENUM_ITEMS) \
                or tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_ITEMS):
            self._in_items = event == 'start'
            return None, None, None
        if tag.matches(self._resource_uri, self._cim_class) \
                or tag.matches(c.XML_NS_WS_MAN, c.WSM_XML_FRAGMENT):
            if event == 'start':
                self._accumulator.new_instance()
            return None, None, None
        return uri, localname, tag


class ExpatResponseHandler(object):

    def __init__(self, logger):
        self._logger = logger

    def handle_response(self, response, resource_uri, cim_class, accumulator):
        parser = sax.make_parser()
        parser.setFeature(sax.handler.feature_namespaces, True)
        handler = WsmanSaxContentHandler(accumulator, resource_uri, cim_class)
        parser.setContentHandler(handler)
        d = defer.Deferred()

        def finished():
            d.callback(handler.enumeration_context)

        reader = AsyncParseReader(parser, self._logger, finished)
        response.deliverBody(reader)
        return d
