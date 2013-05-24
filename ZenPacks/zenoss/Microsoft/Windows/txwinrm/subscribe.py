##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import logging
from collections import namedtuple
from twisted.internet import defer
from . import constants as c
from .util import create_etree_request_sender, get_datetime

log = logging.getLogger('zen.winrm')
_MAX_PULL_REQUESTS_PER_BATCH = 999999

_EVENT_QUERY_FMT = '&lt;QueryList&gt;&lt;Query Path=&quot;{path}&quot;&gt;' \
    '&lt;Select&gt;{select}&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;'

Event = namedtuple('Event', 'system data rendering_info')

System = namedtuple('System', [
    'provider',
    'event_id',
    'event_id_qualifiers',
    'level',
    'task',
    'keywords',
    'time_created',
    'event_record_id',
    'channel',
    'computer',
    'user_id'])

RenderingInfo = namedtuple('RenderingInfo', [
    'culture',
    'message',
    'level',
    'opcode',
    'keywords'])


def _find_subscription_id(subscribe_resp_elem):
    xpath = './/{%s}Identifier' % c.XML_NS_EVENTING
    return subscribe_resp_elem.findtext(xpath).strip()


def _find_enumeration_context(resp_elem):
    xpath = './/{%s}EnumerationContext' % c.XML_NS_ENUMERATION
    return resp_elem.findtext(xpath).strip()


def _event_attr(elem, localname, attr):
    subelem = elem.find('.//{%s}%s' % (c.XML_NS_MSEVENT, localname))
    return None if subelem is None else subelem.get(attr)


def _event_text(elem, localname):
    text = elem.findtext('.//{%s}%s' % (c.XML_NS_MSEVENT, localname))
    return None if text is None else text.strip()


def _event_datetime(elem, localname, attr):
    date_str = _event_attr(elem, localname, attr)
    return get_datetime(date_str)


def _event_list(elem, localname):
    texts = []
    for e in elem.findall('.//{%s}%s' % (c.XML_NS_MSEVENT, localname)):
        texts.append(e.text)
    return texts


def _safe_int(text, base=10):
    return None if text is None else int(text, base)


def _find_events(pull_resp_elem):
    event_elems = pull_resp_elem.findall('.//{%s}Event' % c.XML_NS_MSEVENT)
    for event_elem in event_elems:
        system_elem = event_elem.find('.//{%s}System' % c.XML_NS_MSEVENT)
        ri_elem = event_elem.find('.//{%s}RenderingInfo' % c.XML_NS_MSEVENT)
        system = System(
            provider=_event_attr(system_elem, 'Provider', 'Name'),
            event_id=_safe_int(_event_text(system_elem, 'EventID')),
            event_id_qualifiers=_safe_int(_event_attr(
                system_elem, 'EventID', 'Qualifiers')),
            level=_safe_int(_event_text(system_elem, 'Level')),
            task=_safe_int(_event_text(system_elem, 'Task')),
            keywords=_safe_int(_event_text(system_elem, 'Keywords'), 16),
            time_created=_event_datetime(
                system_elem, 'TimeCreated', 'SystemTime'),
            event_record_id=_safe_int(_event_text(
                system_elem, 'EventRecordID')),
            channel=_event_text(system_elem, 'Channel'),
            computer=_event_text(system_elem, 'Computer'),
            user_id=_event_attr(system_elem, 'Security', 'UserID'))
        if ri_elem is None:
            rendering_info = None
        else:
            rendering_info = RenderingInfo(
                culture=ri_elem.get('Culture'),
                message=_event_text(ri_elem, 'Message'),
                level=_event_text(ri_elem, 'Level'),
                opcode=_event_text(ri_elem, 'Opcode'),
                keywords=_event_list(ri_elem, 'Keyword'))
        yield Event(
            system=system,
            data=_event_text(event_elem, 'Data'),
            rendering_info=rendering_info)


class EventSubscription(object):

    def __init__(self, sender):
        self._sender = sender
        self._subscription_id = None
        self._enumeration_context = None

    def __del__(self):
        log.debug("Deleting EventSubscription object; calling unsubscribe.")
        self.unsubscribe()

    @defer.inlineCallbacks
    def subscribe(self, path='Application', select='*'):
        if self._subscription_id is not None:
            raise Exception('You must unsubscribe first.')
        event_query = _EVENT_QUERY_FMT.format(path=path, select=select)
        resp_elem = yield self._send_subscribe(event_query)
        self._subscription_id = _find_subscription_id(resp_elem)
        self._enumeration_context = _find_enumeration_context(resp_elem)

    @defer.inlineCallbacks
    def _send_subscribe(self, event_query):
        resp_elem = yield self._sender.send_request(
            'subscribe', event_query=event_query)
        defer.returnValue(resp_elem)

    @defer.inlineCallbacks
    def pull(self, process_event_func):
        if self._subscription_id is None:
            raise Exception('You must subscribe first.')
        request_count = 0
        while request_count < _MAX_PULL_REQUESTS_PER_BATCH:
            request_count += 1
            resp_elem = yield self._send_pull(self._enumeration_context)
            self._enumeration_context = _find_enumeration_context(resp_elem)
            found_events = 0
            for event in _find_events(resp_elem):
                found_events += 1
                process_event_func(event)
            if not found_events:
                break
        else:
            raise Exception('Reached max pull requests per batch.')

    @defer.inlineCallbacks
    def _send_pull(self, enumeration_context):
        resp_elem = yield self._sender.send_request(
            'event_pull', enumeration_context=enumeration_context)
        defer.returnValue(resp_elem)

    @defer.inlineCallbacks
    def unsubscribe(self):
        if self._subscription_id is None:
            return
        yield self._send_unsubscribe(self._subscription_id)
        self._subscription_id = None
        self._enumeration_context = None

    @defer.inlineCallbacks
    def _send_unsubscribe(self, subscription_id):
        resp_elem = yield self._sender.send_request(
            'unsubscribe', subscription_id=subscription_id)
        defer.returnValue(resp_elem)


def create_event_subscription(conn_info):
    sender = create_etree_request_sender(conn_info)
    return EventSubscription(sender)
