##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import sys
import logging
from collections import namedtuple
from twisted.internet import defer, task, reactor
from . import app
from .subscribe import create_event_subscription

log = logging.getLogger('zen.winrm')
SubscriptionInfo = namedtuple('SubscriptionInfo', ['path', 'select'])


def subscription_info_repr(self):
    return "{0.path}/'{0.select}'".format(self)

SubscriptionInfo.__repr__ = subscription_info_repr


class SubscriptionInfoBuilder(object):

    def __init__(self, path=None, select=None):
        self.path = path
        self.select = select

    def build(self):
        return SubscriptionInfo(self.path, self.select)


class WecutilStrategy(object):

    def __init__(self):
        self._event_count = 0
        self._d = defer.Deferred()
        self._subscriptions_dct = {}

    @property
    def count_summary(self):
        return '{0} events'.format(self._event_count)

    @defer.inlineCallbacks
    def _do_pull(
            self, i, num_pulls, hostname, subscr_info):
        prefix = "{0} {1}".format(hostname, subscr_info)
        subscription = self._subscriptions_dct[(hostname, subscr_info)]
        if num_pulls > 0 and i == num_pulls:
            yield subscription.unsubscribe()
            del self._subscriptions_dct[(hostname, subscr_info)]
            if not self._subscriptions_dct:
                self._d.callback(None)
            return
        i += 1
        sys.stdout.write('{0} pull #{1}'.format(prefix, i))
        if num_pulls > 0:
            sys.stdout.write(' of {0}'.format(num_pulls))
        print

        def print_event(event):
            self._event_count += 1
            print "{0} {1}".format(prefix, event)

        log.debug("subscription.pull- {0} {1} (start)"
                  .format(hostname, subscr_info))
        yield subscription.pull(print_event)
        log.debug("subscription.pull- {0} {1} (finished)"
                  .format(hostname, subscr_info))
        task.deferLater(reactor, 0, self._do_pull, i, num_pulls, hostname,
                        subscr_info)

    @defer.inlineCallbacks
    def act(self, good_conn_infos, args, config):
        for conn_info in good_conn_infos:
            hostname = conn_info.hostname
            for subscr_info in config.subscr_infos:
                subscription = create_event_subscription(conn_info)
                self._subscriptions_dct[(hostname, subscr_info)] = subscription
                yield subscription.subscribe(
                    subscr_info.path, subscr_info.select)
                self._do_pull(0, args.num_pulls, hostname, subscr_info)
        yield self._d


class WecUtility(app.ConfigDrivenUtility):

    def add_args(self, parser):
        parser.add_argument("--path", "-p", default='Application')
        parser.add_argument("--select", "-s", default='*')
        parser.add_argument("--num-pulls", "-n", type=int, default=2)

    def check_args(self, args):
        return True

    def add_config(self, parser, config):
        subscr_info_builders_dct = {}
        for key, value in parser.items('subscriptions'):
            k1, k2 = key.split('.')
            if k2 not in ['path', 'select']:
                log.error("Illegal subscription key: {0}".format(key))
                continue
            if k1 not in subscr_info_builders_dct:
                subscr_info_builders_dct[k1] = SubscriptionInfoBuilder()
            setattr(subscr_info_builders_dct[k1], k2, value)
        config.subscr_infos = []
        for subscr_info_builder in subscr_info_builders_dct.values():
            config.subscr_infos.append(subscr_info_builder.build())

    def adapt_args_to_config(self, args, config):
        config.subscr_infos = [SubscriptionInfo(args.path, args.select)]

if __name__ == '__main__':
    app.main(WecUtility(WecutilStrategy()))
