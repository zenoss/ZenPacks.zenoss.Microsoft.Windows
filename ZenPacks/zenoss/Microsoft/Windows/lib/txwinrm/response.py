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

from collections import deque
from cStringIO import StringIO

from xml.etree import cElementTree
from xml.etree import ElementTree
from xml import sax

from twisted.internet import defer
from twisted.internet.protocol import Protocol
from twisted.web._newclient import ResponseFailed

from . import contstants as c


class EtreeEventHandler(object):
    """Used by ElementTree and cElementTree parsing"""

    def __init__(self, root, printer, resource_uri, cim_class):
        self._root = root
        self._printer = printer
        self._resource_uri = resource_uri
        self._cim_class = cim_class

    def handle_event(self, event, elem):
        if '}' in elem.tag:
            uri, localname = elem.tag.split('}')
        else:
            uri = ''
            localname = elem.tag
        uri = uri[1:]
        if event == "start":
            if uri.lower() == self._resource_uri.lower() \
                    and localname.lower() == self._cim_class.lower():
                self._printer.new_instance()
            return
        if event == "end":
            if elem.text:
                self._printer.append_element(uri, localname, elem.text)
            self._root.clear()

    def print_elems_with_text(self):
        self._printer.print_elems_with_text()

    @property
    def enumeration_context(self):
        return self._printer.enumeration_context


class AsyncParseReader(Protocol):
    """Used by ElementTree and expat parsing"""

    def __init__(self, xml_parser, finished_func=None):
        self._xml_parser = xml_parser
        self._finished = finished_func
        if finished_func is None:
            self._finished = xml_parser.finished

    def dataReceived(self, data):
        self._xml_parser.feed(data)

    def connectionLost(self, reason):
        if isinstance(reason.value, ResponseFailed):
            print "Connection lost:", reason.value.reasons[0]
        self._finished()


# cElementTree parsing --------------------------------------------------------

class StringIOReader(Protocol):

    def __init__(self):
        self.deferred_string_io = defer.Deferred()
        self._string_io = StringIO()

    def dataReceived(self, data):
        self._string_io.write(data)

    def connectionLost(self, reason):
        if isinstance(reason.value, ResponseFailed):
            print "Connection lost:", reason.value.reasons[0]
        elif c.DEBUG:
            print "Connection lost:", reason.value
        self._string_io.reset()
        self.deferred_string_io.callback(self._string_io)


class cElementTreeResponseHandler(object):

    @defer.inlineCallbacks
    def handle_response(self, response, resource_uri, cim_class, printer):
        reader = StringIOReader()
        response.deliverBody(reader)
        source = yield reader.deferred_string_io
        context = cElementTree.iterparse(source, events=("start", "end"))
        context = iter(context)
        event, root = context.next()
        handler = EtreeEventHandler(root, printer, resource_uri, cim_class)
        for event, elem in context:
            handler.handle_event(event, elem)
        defer.returnValue(handler)


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

    @defer.inlineCallbacks
    def handle_response(self, response, resource_uri, cim_class, printer):
        parser = WsmanElementTreeParser()
        reader = AsyncParseReader(parser)
        response.deliverBody(reader)
        start_event, root = yield parser.get_event()
        handler = EtreeEventHandler(root, printer, resource_uri, cim_class)
        while True:
            event, elem = yield parser.get_event()
            if event is None:
                break
            handler.handle_event(event, elem)
        defer.returnValue(handler)


# sax expat parsing -----------------------------------------------------------

class WsmanSaxContentHandler(sax.handler.ContentHandler):

    def __init__(self, printer, resource_uri, cim_class):
        self._printer = printer
        self._resource_uri = resource_uri
        self._cim_class = cim_class
        self._buffer = StringIO()

    def startElementNS(self, name, qname, attrs):
        uri, localname = name
        if uri is None:
            uri = ''
        if uri.lower() == self._resource_uri.lower() \
                and localname.lower() == self._cim_class.lower():
            self._printer.new_instance()

    def endElementNS(self, name, qname):
        text = self._buffer.getvalue()
        self._buffer.reset()
        self._buffer.truncate()
        if text:
            uri, localname = name
            if uri is None:
                uri = ''
            self._printer.append_element(uri, localname, text)

    def characters(self, content):
        self._buffer.write(content)

    def print_elems_with_text(self):
        self._printer.print_elems_with_text()

    @property
    def enumeration_context(self):
        return self._printer.enumeration_context


class ExpatResponseHandler(object):

    @defer.inlineCallbacks
    def handle_response(self, response, resource_uri, cim_class, printer):
        parser = sax.make_parser()
        parser.setFeature(sax.handler.feature_namespaces, True)
        handler = WsmanSaxContentHandler(printer, resource_uri, cim_class)
        parser.setContentHandler(handler)
        d = defer.Deferred()

        def finished():
            d.callback(None)

        reader = AsyncParseReader(parser, finished)
        response.deliverBody(reader)
        yield d
        defer.returnValue(handler)
