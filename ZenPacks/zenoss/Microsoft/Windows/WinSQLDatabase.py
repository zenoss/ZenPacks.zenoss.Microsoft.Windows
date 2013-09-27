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


class WinSQLDatabase(OSComponent):
    '''
    Model class for MSSQL Database.
    '''
    meta_type = portal_type = 'WinDatabase'

    instancename = None
    version = None
    owner = None
    lastbackupdate = None
    lastlogbackupdate = None
    isaccessible = None
    collation = None
    createdate = None
    defaultfilegroup = None
    primaryfilepath = None

    _properties = OSComponent._properties + (
        {'id': 'instancename', 'type': 'string'},
        {'id': 'version', 'type': 'string'},
        {'id': 'owner', 'type': 'string'},
        {'id': 'lastbackupdate', 'type': 'string'},
        {'id': 'lastlogbackupdate', 'type': 'string'},
        {'id': 'isaccessible', 'type': 'string'},
        {'id': 'collation', 'type': 'string'},
        {'id': 'createdate', 'type': 'string'},
        {'id': 'defaultfilegroup', 'type': 'string'},
        {'id': 'primaryfilepath', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("winsqlinstance", ToOne(ToManyCont,
            "ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance",
            "databases")),
    )

    def getRRDTemplateName(self):
        return 'WinDatabase'

InitializeClass(WinSQLDatabase)
