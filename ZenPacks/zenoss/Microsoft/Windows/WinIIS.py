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


class WinIIS(OSComponent):
    '''
    Model class for Windows Internet Information Service (IIS).
    '''
    meta_type = portal_type = 'WinRMIIS'

    sitename = None
    apppool = None
    caption = None
    status = None
    statusname = None
    iis_version = None

    _properties = OSComponent._properties + (
        {'id': 'sitename', 'label': 'Site Name', 'type': 'string'},
        {'id': 'apppool', 'label': 'Application Pool', 'type': 'string'},
        {'id': 'caption', 'label': 'Caption', 'type': 'string'},
        {'id': 'status', 'label': 'Status', 'type': 'string'},
        {'id': 'statusname', 'label': 'Status Name', 'type': 'string'},
        {'id': 'iis_version', 'type': 'int'},
    )

    _relations = OSComponent._relations + (
        ("os", ToOne(ToManyCont,
         "ZenPacks.zenoss.Microsoft.Windows.OperatingSystem",
         "winrmiis")),
    )

    def getRRDTemplateName(self):
        return 'IISSites'

    def getIconPath(self):
        '''
        Return the path to an icon for this component.
        '''
        return '/++resource++mswindows/img/WinIIS.png'


InitializeClass(WinIIS)
