##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging

log = logging.getLogger("zen.MicrosoftWindows")
from Products.ZenModel.IpInterface import IpInterface
from Products.ZenRelations.RelSchema import ToManyCont, ToOne


class TeamInterface(IpInterface):
    portal_type = meta_type = 'WinTeamInterface'

    _relations = IpInterface._relations + (
        ('os', ToOne(ToManyCont,
            'ZenPacks.zenoss.Microsoft.Windows.OperatingSystem',
            'teaminterfaces')),
        )
