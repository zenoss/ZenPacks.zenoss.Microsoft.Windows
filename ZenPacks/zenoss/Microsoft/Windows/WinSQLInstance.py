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


class WinSQLInstance(OSComponent):
    '''
    Model class for MSSQL Instance.
    '''
    meta_type = portal_type = 'WinDBInstance'

    instancename = None
    backupdevices = None
    roles = None

    _properties = OSComponent._properties + (
        {'id': 'instancename', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("os", ToOne(ToManyCont,
            "ZenPacks.zenoss.Microsoft.Windows.OperatingSystem",
            "winsqlinstances")),
        ("backups", ToManyCont(ToOne,
            "ZenPacks.zenoss.Microsoft.Windows.WinSQLBackup",
            "winsqlinstance")),
        ("jobs", ToManyCont(ToOne,
            "ZenPacks.zenoss.Microsoft.Windows.WinSQLJob",
            "winsqlinstance")),
        ("databases", ToManyCont(ToOne,
            "ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase",
            "winsqlinstance")),
    )

    def getRRDTemplateName(self):
        return 'WinDBInstance'

InitializeClass(WinSQLInstance)
