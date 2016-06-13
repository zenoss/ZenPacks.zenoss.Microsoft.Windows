##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.error import TimeoutError


def add_timeout(deferred, timeout):
    '''
    Raise TimeoutError on deferred after timeout seconds.

    Returns original deferred.
    '''
    def timeout_deferred():
        if not deferred.called:
            deferred.errback(TimeoutError())

    timeout_d = reactor.callLater(timeout, timeout_deferred)

    def cancel_timeout_d(result):
        if not timeout_d.called:
            timeout_d.cancel()

        return result

    deferred.addBoth(cancel_timeout_d)

    return deferred


def sleep(seconds):
    '''
    Return a deferred that is called in given seconds.
    '''
    d = Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d
