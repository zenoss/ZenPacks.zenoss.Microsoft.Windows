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

    instancename = None
    jobid = None
    enabled = None
    description = None
    username = None
    datecreated = None

    _properties = OSComponent._properties + (
        {'id': 'instancename', 'label': 'Instance Name', 'type': 'string'},
        {'id': 'jobid', 'label': 'Job ID', 'type': 'string'},
        {'id': 'enabled', 'label': 'Enabled', 'type': 'string'},
        {'id': 'description', 'label': 'Description', 'type': 'string'},
        {'id': 'username', 'label': 'User', 'type': 'string'},
        {'id': 'datecreated', 'label': 'Date Created', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("winsqlinstance", ToOne(ToManyCont,
            "ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance",
            "jobs")),
    )

    def getRRDTemplateName(self):
        return 'WinSQLJob'

InitializeClass(WinSQLJob)
