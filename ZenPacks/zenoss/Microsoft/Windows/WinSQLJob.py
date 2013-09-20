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


class WinSQLJob(OSComponent):
    '''
    Model class for MSSQLJobs.
    '''
    meta_type = portal_type = 'WinSQLJob'

    sitename = None

    _properties = OSComponent._properties + (
        {'id': 'sitename', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("os", ToOne(ToManyCont,
         "ZenPacks.zenoss.Microsoft.Windows.OperatingSystem",
         "winsqljob")),
    )

    def getRRDTemplateName(self):
        return 'WinSQLJob'

InitializeClass(WinSQLJob)
