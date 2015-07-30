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


    #startmode [string] = The start mode for the servicename
    #account [string] = The account name the service runs as
    #usermonitor [boolean] = Did user manually set monitor.

    servicename = None
    caption = None
    description = None
    startmode = None
    account = None
    monitor = False
    usermonitor = False

    _properties = OSComponent._properties + (
        {'id': 'servicename', 'label': 'Service Name', 'type': 'string'},
        {'id': 'caption', 'label': 'Caption', 'type': 'string'},
        {'id': 'description', 'label': 'Description', 'type': 'string'},
        {'id': 'startmode', 'label': 'Start Mode', 'type': 'string'},
        {'id': 'account', 'label': 'Account', 'type': 'string'},
        {'id': 'usermonitor', 'label': 'User Selected Monitor State',
            'type': 'boolean'},
        )

    _relations = OSComponent._relations + (
        ("os", ToOne(ToManyCont,
         "ZenPacks.zenoss.Microsoft.Windows.OperatingSystem",
         "winrmservices")),
    )

    def getRRDTemplateName(self):
        try:
            if self.getRRDTemplateByName(self.servicename):
                return self.servicename
        except TypeError:
            pass
        return 'WinService'

    def monitored(self):
        """Return True if this service should be monitored. False otherwise."""

        # 1 - Check to see if the user has manually set monitor status
        if self.usermonitor is True:
            return self.monitor

        # 2 - Check what our template says to do.
        template = self.getRRDTemplate()
        if template:
            datasource = template.datasources._getOb('DefaultService', None)
            if datasource:
                for startmode in datasource.startmode.split(','):
                    if startmode in self.startmode.split(','):
                        return True

        return False


InitializeClass(WinService)
