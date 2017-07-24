##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

# twisted 11 doesn't have this error
try:
    from twisted.web._newclient import ResponseNeverReceived
except ImportError:
    ResponseNeverReceived = str
    pass
from twisted.internet.error import ConnectionLost


def send_to_debug(error):
    try:
        reason = error.value.reasons[0].value
    except Exception:
        reason = ''
    # if ConnectionLost or ResponseNeverReceived, more than
    # likely zenpython stopping.  throw messages to debug
    try:
        if isinstance(reason, ConnectionLost) or\
           isinstance(error.value, ResponseNeverReceived):
            return True
    except AttributeError:
        pass
    return False
