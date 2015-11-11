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
    cluster_node_server = None
    recoverymodel = None
    systemobject = None
    status = None

    _properties = OSComponent._properties + (
        {'id': 'instancename', 'label': 'Instance Name', 'type': 'string'},
        {'id': 'version', 'label': 'Version', 'type': 'string'},
        {'id': 'owner', 'label': 'Owner', 'type': 'string'},
        {'id': 'lastbackupdate', 'label': 'Last Backup', 'type': 'string'},
        {'id': 'lastlogbackupdate', 'label': 'Last Log Backup',
            'type': 'string'},
        {'id': 'isaccessible', 'label': 'Accessible', 'type': 'string'},
        {'id': 'collation', 'label': 'Collation', 'type': 'string'},
        {'id': 'createdate', 'label': 'Created On', 'type': 'string'},
        {'id': 'defaultfilegroup', 'label': 'File Group', 'type': 'string'},
        {'id': 'primaryfilepath', 'label': 'File Path', 'type': 'string'},
        {'id': 'systemobject', 'label': 'System Object', 'type': 'string'},
        {'id': 'recoverymodel', 'label': 'Recovery Model', 'type': 'string'},
        {'id': 'status', 'label': 'Status', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("winsqlinstance", ToOne(ToManyCont,
            "ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance",
            "databases")),
    )

    def getRRDTemplateName(self):
        return 'WinDatabase'

InitializeClass(WinSQLDatabase)
