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

    _properties = OSComponent._properties + (
        {'id': 'sitename', 'type': 'string'},
        {'id': 'apppool', 'type': 'string'},
        {'id': 'caption', 'type': 'string'},
        {'id': 'status', 'type': 'string'},
        {'id': 'statusname', 'type': 'string'},
                )

    _relations = OSComponent._relations + (
        ("os", ToOne(ToManyCont,
         "ZenPacks.zenoss.Microsoft.Windows.OperatingSystem",
         "winrmiis")),
    )

    def getRRDTemplateName(self):
        return 'IISSites'

InitializeClass(WinIIS)
