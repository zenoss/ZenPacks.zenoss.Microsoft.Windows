##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017 all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import re

from zope.interface import implements
from Products.ZenEvents.interfaces import IPostEventPlugin
from Products.ZenEvents import ZenEventClasses


PATTERN = re.compile("address.*not found")


class UpdateDNSErrorEvent(object):
    """
    Update event message with additional information in case we get "DNS lookup failed".
    """
    implements(IPostEventPlugin)

    @staticmethod
    def apply(evt, dmd):
        if evt.severity == ZenEventClasses.Clear:
            return

        if evt.DeviceClass and '/Server/Microsoft/Windows' in evt.DeviceClass or \
                '/Server/Microsoft/Cluster' in evt.DeviceClass:
            if PATTERN.search(evt.message):
                clarity = ' Please check configuration of zWinRMServerName property and check the DNS server settings.'
                evt.message = evt.message + clarity
