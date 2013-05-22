##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

"""
This module contains the code responsible for constructing WinRM enumeration
and pull requests containing WQL queries. The responses are parsed with the
result being a list of item objects. The item objects have a dynamic set of
attributes, even within the same query. Some of the Win32_* CIM classes have
optional properties, and a 'select *' query will return those attributes only
on the items that have them. Some of the items returned might be subclasses of
the CIM class mentioned in the query and contain additional attributes. The
attributes of the returned item objects follow these rules

    * nil values are None
    * empty values are empty
    * text values are strings
    * numeric values are strings ready to be sent through int() or float()
    * missing values are missing
    * array values are lists
    * date values are datetime objects
"""

import logging
from cStringIO import StringIO
from collections import deque
from pprint import pformat
from xml import sax
from twisted.internet import defer
from twisted.internet.protocol import Protocol
from twisted.web.client import ResponseFailed
from . import constants as c
from .util import RequestSender, get_datetime

log = logging.getLogger('zen.winrm')
_MAX_REQUESTS_PER_ENUMERATION = 9999
_DEFAULT_RESOURCE_URI = '{0}/*'.format(c.WMICIMV2)
_MARKER = object()


class WinrmClient(object):
    """
    Sends enumerate requests to a host running the WinRM service and returns
    a list of items.
    """

    def __init__(self, sender, handler):
        self._sender = sender
        self._handler = handler
        self._hostname = sender.hostname

    @defer.inlineCallbacks
    def enumerate(self, wql, resource_uri=_DEFAULT_RESOURCE_URI):
        """
        Runs a remote WQL query.
        """
        request_template_name = 'enumerate'
        enumeration_context = None
        items = []
        try:
            for i in xrange(_MAX_REQUESTS_PER_ENUMERATION):
                log.debug('{0} "{1}" {2}'.format(
                    self._hostname, wql, request_template_name))
                response = yield self._sender.send_request(
                    request_template_name,
                    resource_uri=resource_uri,
                    wql=wql,
                    enumeration_context=enumeration_context)
                log.debug("{0} HTTP status: {1}".format(
                    self._hostname, response.code))
                enumeration_context, new_items = \
                    yield self._handler.handle_response(response)
                items.extend(new_items)
                if not enumeration_context:
                    break
                request_template_name = 'pull'
            else:
                raise Exception("Reached max requests per enumeration.")
        except ResponseFailed as e:
            for reason in e.reasons:
                log.error('{0} {1}'.format(self._hostname, reason.value))
            raise
        except Exception as e:
            log.error('{0} {1}'.format(self._hostname, e))
            raise
        defer.returnValue(items)


def create_winrm_client(conn_info):
    """
    Constructs a WinRM client with the default response handler.
    """
    sender = RequestSender(conn_info)
    return WinrmClient(sender, SaxResponseHandler())


def create_parser_and_factory():
    """
    Sets up the SAX XML parser and returns it along with an
    EnvelopeHandlerFactory instance that has access to the enumeration-context
    and items of each WinRM response.
    """
    parser = sax.make_parser()
    parser.setFeature(sax.handler.feature_namespaces, True)
    text_buffer = TextBufferingContentHandler()
    factory = EnvelopeHandlerFactory(text_buffer)
    content_handler = ChainingContentHandler([
        text_buffer,
        DispatchingContentHandler(factory)])
    parser.setContentHandler(content_handler)
    return parser, factory


class SaxResponseHandler(object):
    """
    The default response handler.
    """

    @defer.inlineCallbacks
    def handle_response(self, response):
        """
        Given a Twisted response object, parse it and return the
        enumeration-context and items.
        """
        parser, factory = create_parser_and_factory()
        proto = ParserFeedingProtocol(parser)
        response.deliverBody(proto)
        yield proto.d
        defer.returnValue((factory.enumeration_context, factory.items))


def safe_lower_equals(left, right):
    """
    Determine case-insensitive equality while checking for Nones.
    """
    left_l, right_l = [None if s is None else s.lower() for s in left, right]
    return left_l == right_l


class TagComparer(object):
    """
    Compares namespaced XML tags.
    """

    def __init__(self, uri, localname):
        self.uri = uri
        self.localname = localname

    def matches(self, uri, localname):
        """
        Does this tag match the uri/localname passed in?
        """
        return safe_lower_equals(self.uri, uri) \
            and safe_lower_equals(self.localname, localname)

    def __repr__(self):
        return str((self.uri, self.localname))


def create_tag_comparer(name):
    """
    Construct a TagComparer instance given a uri/localname pair
    """
    uri, localname = name
    return TagComparer(uri, localname)


class ChainingProtocol(Protocol):
    """
    A Twisted Protocol that dispatches calls to all the sub-protocols in its
    chain.
    """

    def __init__(self, chain):
        self._chain = chain
        self.d = defer.DeferredList([p.d for p in chain])

    def dataReceived(self, data):
        """
        Called from Twisted when data is received.
        """
        for protocol in self._chain:
            protocol.dataReceived(data)

    def connectionLost(self, reason):
        """
        Called from Twisted indicating that dataReceived has been called for
        the last time.
        """
        for protocol in self._chain:
            protocol.connectionLost(reason)


class ParserFeedingProtocol(Protocol):
    """
    A Twisted Protocol that feeds an XML parser as data is received.
    """

    def __init__(self, xml_parser):
        self._xml_parser = xml_parser
        self.d = defer.Deferred()
        self._debug_data = ''

    def dataReceived(self, data):
        """
        Called from Twisted when data is received.
        """
        if log.isEnabledFor(logging.DEBUG):
            self._debug_data += data
            log.debug("ParserFeedingProtocol dataReceived {0}"
                      .format(data))
        self._xml_parser.feed(data)

    def connectionLost(self, reason):
        """
        Called from Twisted indicating that dataReceived has been called for
        the last time.
        """
        if self._debug_data and log.isEnabledFor(logging.DEBUG):
            try:
                import xml.dom.minidom
                xml = xml.dom.minidom.parseString(self._debug_data)
                log.debug(xml.toprettyxml())
            except:
                log.debug('Could not prettify response XML: "{0}"'
                          .format(self._debug_data))
        if isinstance(reason.value, ResponseFailed):
            log.error("Connection lost: {0}".format(reason.value.reasons[0]))
        self.d.callback(None)


class ChainingContentHandler(sax.handler.ContentHandler):
    """
    A SAX content handler that dispatches the SAX callbacks to each of the
    sub-handlers in its chain.
    """

    def __init__(self, chain):
        self._chain = chain

    def startElementNS(self, name, qname, attrs):
        """
        A SAX callback indicating the start of an element. Includes namespace
        information.
        """
        for handler in self._chain:
            handler.startElementNS(name, qname, attrs)

    def endElementNS(self, name, qname):
        """
        A SAX callback indicating the end of an element. Includes namespace
        information.
        """
        for handler in self._chain:
            handler.endElementNS(name, qname)

    def characters(self, content):
        """
        A SAX callback indicating characters from the text portion of the
        current XML element.
        """
        for handler in self._chain:
            handler.characters(content)


class TextBufferingContentHandler(sax.handler.ContentHandler):
    """
    Keeps track of the text in the current XML element.
    """

    def __init__(self):
        self._buffer = StringIO()
        self._text = None

    @property
    def text(self):
        """
        Read-only access to the current element's text.
        """
        return self._text

    def startElementNS(self, name, qname, attrs):
        """
        A SAX callback indicating the start of an element. Includes namespace
        information.

        This implementation resets and truncates the buffer.
        """
        self._reset_truncate()

    def endElementNS(self, name, qname):
        """
        A SAX callback indicating the end of an element. Includes namespace
        information.

        This implementation saves the text from the buffer. Then it resets and
        truncates the buffer.
        """
        self._text = self._buffer.getvalue()
        self._reset_truncate()

    def characters(self, content):
        """
        A SAX callback indicating characters from the text portion of the
        current XML element.

        This implementation writes to the buffer.
        """
        self._buffer.write(content.encode('utf8', 'ignore').strip())

    def _reset_truncate(self):
        self._buffer.reset()
        self._buffer.truncate()


class DispatchingContentHandler(sax.handler.ContentHandler):
    """
    A SAX content handler that dispatches the SAX parsing callbacks to
    sub-handlers based on the tag. It only looks for a sub-handler if one isn't
    already active. The subhandler remains active until the tag which made it
    active is closed.
    """

    def __init__(self, subhandler_factory):
        self._subhandler_factory = subhandler_factory
        self._subhandler_tag = None
        self._subhandler = None

    def startElementNS(self, name, qname, attrs):
        """
        A SAX callback indicating the start of an element. Includes namespace
        information.

        This implementation dispatches to the sub-handler based on the tag.
        """
        log.debug('DispatchingContentHandler startElementNS {0} {1} {2}'
                  .format(name, self._subhandler, self._subhandler_tag))
        if self._subhandler is None:
            self._subhandler, tag = self._get_subhandler_for(name)
            if self._subhandler is not None:
                self._subhandler_tag = tag
                log.debug('new subhandler {0} {1}'
                          .format(self._subhandler, self._subhandler_tag))

        if self._subhandler is not None:
            self._subhandler.startElementNS(name, qname, attrs)

    def endElementNS(self, name, qname):
        """
        A SAX callback indicating the end of an element. Includes namespace
        information.

        This implementation dispatches to the sub-handler based on the tag.
        """
        log.debug('DispatchingContentHandler endElementNS {0} {1}'
                  .format(name, self._subhandler))
        if self._subhandler is not None:
            self._subhandler.endElementNS(name, qname)
        if self._subhandler_tag is not None:
            uri, localname = name
            if self._subhandler_tag.matches(uri, localname):
                self._subhandler_tag = None
                self._subhandler = None
                log.debug('removed subhandler')

    def _get_subhandler_for(self, name):
        tag = create_tag_comparer(name)
        return self._subhandler_factory.get_handler_for(tag), tag


def is_end_of_sequence(tag):
    """
    Is this tag an enumeration end-of-sequence tag. The namespace varies
    between 'select *' queries and queries that explicitly list properties.
    """
    return tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_END_OF_SEQUENCE) \
        or tag.matches(c.XML_NS_WS_MAN, c.WSENUM_END_OF_SEQUENCE)


class EnvelopeHandlerFactory(object):
    """
    Supplies enumeration-context and items sub-handlers to the dispatching
    handler.
    """

    def __init__(self, text_buffer):
        self._enumerate_handler = EnumerateContentHandler(text_buffer)
        self._items_handler = ItemsContentHandler(text_buffer)

    @property
    def enumeration_context(self):
        """
        Read-only access to the enumeration context. Returns None if the
        response indicated end-of-sequence.
        """
        return self._enumerate_handler.enumeration_context

    @property
    def items(self):
        """
        The items found in the WinRM response.
        """
        return self._items_handler.items

    def get_handler_for(self, tag):
        """
        Return the subhandler that should be activated for the given XML tag.
        """
        handler = None
        if tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_ENUMERATION_CONTEXT) \
                or is_end_of_sequence(tag):
            handler = self._enumerate_handler
        elif tag.matches(c.XML_NS_WS_MAN, c.WSENUM_ITEMS) \
                or tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_ITEMS):
            handler = self._items_handler
        log.debug('EnvelopeHandlerFactory get_handler_for {0} {1}'
                  .format(tag, handler))
        return handler


class EnumerateContentHandler(sax.handler.ContentHandler):
    """
    A SAX content handler that keeps track of the enumeration-context and
    end-of-sequence elements in a WinRM response.
    """

    def __init__(self, text_buffer):
        self._text_buffer = text_buffer
        self._enumeration_context = None
        self._end_of_sequence = False

    @property
    def enumeration_context(self):
        """
        Read-only access to the enumeration context. Returns None if the
        response indicated end-of-sequence.
        """
        if not self._end_of_sequence:
            return self._enumeration_context

    def endElementNS(self, name, qname):
        """
        A SAX callback indicating the end of an element. Includes namespace
        information.

        This implementation records the enumeration-context and
        end-of-sequence values.
        """
        tag = create_tag_comparer(name)
        if tag.matches(c.XML_NS_ENUMERATION, c.WSENUM_ENUMERATION_CONTEXT):
            self._enumeration_context = self._text_buffer.text
        if is_end_of_sequence(tag):
            self._end_of_sequence = True


class AddPropertyWithoutItemError(Exception):
    """
    Raised when add_property is called before new_item on a ItemsAccumulator.
    """

    def __init__(self, msg):
        Exception.__init__(self, "It is an illegal state for add_property to "
                                 "be called before the first call to new_item."
                                 " {0}".format(msg))


class Item(object):
    """
    A flexible object for storing the properties of the items returned by a WQL
    query.
    """

    def __repr__(self):
        return '\n' + pformat(vars(self), indent=4)


class ItemsAccumulator(object):
    """
    new_item() is called each time a new item is recognized in the
    enumerate and pull responses. add_property(name, value) is called with
    each property. All properties added between calls to new_item
    belong to a single item. It is an illegal state for add_property to
    be called before the first call to new_item. add_property being called
    multiple times with the same name within the same item indicates that
    the property is an array.
    """

    def __init__(self):
        self._items = []

    @property
    def items(self):
        """
        The items contained in the response.
        """
        return self._items

    def new_item(self):
        """
        Indicates that a new item was recognized in the response XML.
        Subsequent calls to add_property belong to this item.
        """
        self._items.append(Item())

    def add_property(self, name, value):
        """
        Add a property to the current item. Includes special handling for array
        types.
        """
        if not self._items:
            raise AddPropertyWithoutItemError(
                "{0} = {1}".format(name, value))
        item = self._items[-1]
        prop = getattr(item, name, _MARKER)
        if prop is _MARKER:
            setattr(item, name, value)
            return
        if isinstance(prop, list):
            prop.append(value)
            return
        setattr(item, name, [prop, value])


class TagStackStateError(Exception):
    """
    Raised when the ItemsContentHandler tag stack is in an illegal state. This
    would indicate a bug, because the SAX handler will catch problems in the
    XML document.
    """
    pass


class ItemsContentHandler(sax.handler.ContentHandler):
    """
    A SAX content handler that handles the list of items in the WinRM response.
    For the most part the tag's localname is the property name and the
    element's text is the value. Special handling is necessary for dates and
    nils. Basically the XML handled by this class looks like

        <Items>
            <(Win32_*|XmlFragment)>
                <text-property>value</text-property>
                <date-property>
                    <date>value</date>
                </date-property>
                <nil-property nil="true" />
                <array-property>value1</array-property>
                <array-property>value2</array-property>
            </(Win32_*|XmlFragment)>
        </Items>

    """

    def __init__(self, text_buffer):
        self._text_buffer = text_buffer
        self._accumulator = ItemsAccumulator()
        self._tag_stack = deque()
        self._value = None

    @property
    def items(self):
        """
        The list of items from the WinRM enumerate response.
        """
        return self._accumulator.items

    def startElementNS(self, name, qname, attrs):
        """
        A SAX callback indicating the start of an element. Includes namespace
        information.

        This instance manipulates the tag stack, creating a new instance if
        it's length is 1. Saves value as None if the nil attribute is present.
        """
        log.debug('ItemsContentHandler startElementNS {0} v="{1}" t="{2}" {3}'
                  .format(name, self._value, self._text_buffer.text,
                          self._tag_stack))
        tag = create_tag_comparer(name)
        if len(self._tag_stack) > 3:
            raise Exception("tag stack too long: {0} {1}"
                            .format([t.localname for t in self._tag_stack],
                                    tag.localname))
        if len(self._tag_stack) == 1:
            self._accumulator.new_item()
        elif len(self._tag_stack) == 2:
            if attrs.get((c.XML_NS_BUILTIN, c.BUILTIN_NIL), None) == 'true':
                self._value = (None,)
        self._tag_stack.append(tag)

    def endElementNS(self, name, qname):
        """
        A SAX callback indicating the end of an element. Includes namespace
        information.

        This instance adds properties to the item accumulator depending on the
        length of the tag stack. If the length of the tag stack is 3 it parses
        the text as a date and saves it for later use when the properties
        element is closed.
        """
        log.debug('ItemsContentHandler endElementNS {0} v="{1}" t="{2}" {3}'
                  .format(name, self._value, self._text_buffer.text,
                          self._tag_stack))
        tag = create_tag_comparer(name)
        popped_tag = self._tag_stack.pop()
        if not popped_tag.matches(tag.uri, tag.localname):
            raise TagStackStateError(
                "End of {0} when expecting {1}"
                .format(tag.localname, popped_tag.localname))
        log.debug("ItemsContentHandler endElementNS tag_stack: {0}"
                  .format(self._tag_stack))
        if len(self._tag_stack) == 2:
            if self._value is None:
                value = self._text_buffer.text
            else:
                value = self._value[0]
            self._accumulator.add_property(tag.localname, value)
            self._value = None
        elif len(self._tag_stack) == 3:
            if tag.matches(c.XML_NS_CIM_SCHEMA, "Datetime") \
                    or tag.matches(None, "Datetime"):
                self._value = (get_datetime(self._text_buffer.text),)
