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


class WinSQLBackup(OSComponent):
    '''
    Model class for MSSQL Backup Device Status.
    '''
    meta_type = portal_type = 'WinBackupDevice'

    devicetype = None
    physicallocation = None
    status = None
    instancename = None

    _properties = OSComponent._properties + (
        {'id': 'devicetype', 'type': 'string'},
        {'id': 'physicallocation', 'type': 'string'},
        {'id': 'status', 'type': 'string'},
        {'id': 'instancename', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("winsqlinstance", ToOne(ToManyCont,
            "ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance",
            "backups")),
    )

    def getRRDTemplateName(self):
        return 'WinBackupDevice'

InitializeClass(WinSQLBackup)
