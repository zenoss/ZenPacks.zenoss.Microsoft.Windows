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
    usermonitor [boolean] = That last update to monitor the user made.
    """
    servicename = None
    caption = None
    description = None
    startmode = None
    account = None
    state = None
    monitor = False
    usermonitor = False

    _properties = OSComponent._properties + (
        {'id': 'servicename', 'type': 'string'},
        {'id': 'caption', 'type': 'string'},
        {'id': 'description', 'type': 'string'},
        {'id': 'startmode', 'type': 'string'},
        {'id': 'account', 'type': 'string'},
        {'id': 'state', 'type': 'string'},
        {'id': 'usermonitor', 'type': 'boolean'},
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

    def getBest(self):
        # Method to find template that matches this service
        # Gets the monitor value
        try:
            if self.getRRDTemplateByName(self.servicename):
                template = self.getRRDTemplateByName(self.servicename)
                if template.datasources.DefaultService.defaultgraph == True:
                    return True
            return False
        except:
            return False

    def monitored(self):
        # 1 - Check to see if the user has manually set monitor status
        if self.usermonitor == True:
            return self.monitor

        # 2 - Check to see if a default template exists with default set
        best_template = self.getBest()

        if best_template == True:
            self.monitor = True
            return True
        # 3 - Default to what the current monitor status is
        elif self.monitor == True:
            return True

        # 4 - Nothing is setup for this service to be monitored.
        return False

InitializeClass(WinService)
