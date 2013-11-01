##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


from Globals import InitializeClass

from Products.ZenModel.OSComponent import OSComponent
from Products.ZenModel.IpInterface import IpInterface
from Products.ZenRelations.RelSchema import ToManyCont, ToMany, ToOne


class TeamInterface(IpInterface, OSComponent):
    meta_type = portal_type = 'WinTeamInterface'

    numofnics = None

    _properties = IpInterface._properties + (
        {'id': 'numofnics', 'type': 'string', 'mode': 'w'},
        )

    _relations = OSComponent._relations + (
        ('os', ToOne(ToManyCont,
            'ZenPacks.zenoss.Microsoft.Windows.OperatingSystem',
            'teaminterfaces')),
        ("ipaddresses", ToMany(ToOne, "Products.ZenModel.IpAddress", "interface")),
        ("iproutes", ToMany(ToOne, "Products.ZenModel.IpRouteEntry", "interface")),
        )


InitializeClass(TeamInterface)
