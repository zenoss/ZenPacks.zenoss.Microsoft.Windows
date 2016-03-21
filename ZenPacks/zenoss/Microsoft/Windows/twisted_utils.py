##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from twisted.internet import reactor
from twisted.internet import defer
from twisted.internet.error import TimeoutError

OPERATION_TIMEOUT = 60


def add_timeout(deferred, seconds):
    """Raise TimeoutError on deferred after seconds.

    Returns original deferred.

    """

    def handle_timeout():
        deferred.cancel()

    timeout_d = reactor.callLater(seconds, handle_timeout)

    def handle_result(result):
        if timeout_d.active():
            timeout_d.cancel()

        return result

    deferred.addBoth(handle_result)

    def handle_failure(failure):
        if failure.check(defer.CancelledError):
            raise TimeoutError(string="timeout after %s seconds" % seconds)

        return failure

    deferred.addErrback(handle_failure)
    return deferred


def sleep(seconds):
    '''
    Return a deferred that is called in given seconds.
    '''
    d = defer.Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d
