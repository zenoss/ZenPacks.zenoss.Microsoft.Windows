##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Globals import InitializeClass

from Products.ZenModel.OSComponent import OSComponent
from Products.ZenRelations.RelSchema import ToOne, ToManyCont


class WinService(OSComponent):
    '''
    Model class for Windows Service.
    '''
    meta_type = portal_type = 'WinRMService'

    servicename = None
    caption = None
    description = None
    startmode = None
    account = None
    state = None

    _properties = OSComponent._properties + (
        {'id': 'servicename', 'type': 'string'},
        {'id': 'caption', 'type': 'string'},
        {'id': 'description', 'type': 'string'},
        {'id': 'startmode', 'type': 'string'},
        {'id': 'account', 'type': 'string'},
        {'id': 'state', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("os", ToOne(ToManyCont,
         "ZenPacks.zenoss.Microsoft.Windows.OperatingSystem",
         "winrmservices")),
    )

InitializeClass(WinService)
