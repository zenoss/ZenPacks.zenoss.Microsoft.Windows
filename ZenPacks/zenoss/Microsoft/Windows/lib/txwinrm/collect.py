##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from twisted.internet import defer
from .enumerate import create_winrm_client


class WinrmCollectClient(object):

    @defer.inlineCallbacks
    def do_collect(self, hostname, username, password, wqls):
        client = create_winrm_client(hostname, username, password)
        items = {}
        for wql in wqls:
            items[wql] = yield client.enumerate(wql)
        defer.returnValue(items)


# ----- An example of useage...

if __name__ == '__main__':
    from pprint import pprint
    import logging
    from twisted.internet import reactor
    logging.basicConfig()
    winrm = WinrmCollectClient()

    @defer.inlineCallbacks
    def do_example_collect():
        items = yield winrm.do_collect(
            "gilroy", "Administrator", "Z3n0ss",
            ['Select Caption, DeviceID, Name From Win32_Processor',
             'select Name, Label, Capacity from Win32_Volume'])
        pprint(items)
        reactor.stop()

    reactor.callWhenRunning(do_example_collect)
    reactor.run()
