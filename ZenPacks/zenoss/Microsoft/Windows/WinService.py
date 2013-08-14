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

    """
    startmode [string] = The start mode for the servicename
    account [string] = The account name the service runs as
    state [string] = The current running state of the service
    lastmonitorstatus [boolean] = That last update to monitor the user made.
    """
    servicename = None
    caption = None
    description = None
    startmode = None
    account = None
    state = None
    lastmonitorstatus = False

    _properties = OSComponent._properties + (
        {'id': 'servicename', 'type': 'string'},
        {'id': 'caption', 'type': 'string'},
        {'id': 'description', 'type': 'string'},
        {'id': 'startmode', 'type': 'string'},
        {'id': 'account', 'type': 'string'},
        {'id': 'state', 'type': 'string'},
        {'id': 'lastmonitorstatus', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("os", ToOne(ToManyCont,
         "ZenPacks.zenoss.Microsoft.Windows.OperatingSystem",
         "winrmservices")),
    )

    def getRRDTemplateName(self):
        if self.getRRDTemplateByName(self.servicename):
            return self.servicename
        else:
            return 'WinService'

    def monitored(self):

        return self.monitor

InitializeClass(WinService)
