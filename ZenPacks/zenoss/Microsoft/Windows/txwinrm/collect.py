##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

from collections import namedtuple
from twisted.internet import defer
from .enumerate import create_winrm_client, DEFAULT_RESOURCE_URI
from .util import ConnectionInfo


EnumInfo = namedtuple('EnumInfo', ['wql', 'resource_uri'])


def create_enum_info(wql, resource_uri=DEFAULT_RESOURCE_URI):
    return EnumInfo(wql, resource_uri)


class WinrmCollectClient(object):

    @defer.inlineCallbacks
    def do_collect(self, conn_info, enum_infos):
        """
        conn_info has the following attributes
            hostname
            auth_type: basic or kerberos
            username
            password
            scheme: http (https coming soon)
            port: int
        """
        client = create_winrm_client(conn_info)
        items = {}
        for enum_info in enum_infos:
            items[enum_info] = yield client.enumerate(enum_info.wql, enum_info.resource_uri)
        defer.returnValue(items)


# ----- An example of useage...

if __name__ == '__main__':
    from pprint import pprint
    from getpass import getpass
    import logging
    from twisted.internet import reactor
    logging.basicConfig()
    winrm = WinrmCollectClient()

    @defer.inlineCallbacks
    def do_example_collect():
        conn_info = ConnectionInfo(
            "gilroy", "basic", "Administrator", getpass(), "http", 5985)
        items = yield winrm.do_collect(
            conn_info,
            [create_enum_info('Select Caption, DeviceID, Name From Win32_Processor'),
             create_enum_info('select Name, Label, Capacity from Win32_Volume')])
        pprint(items)
        reactor.stop()

    reactor.callWhenRunning(do_example_collect)
    reactor.run()

