##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Globals import InitializeClass
from socket import gaierror
import logging

from Products.ZenModel.OSComponent import OSComponent
from Products.ZenRelations.RelSchema import ToOne, ToManyCont
from Products.ZenUtils.IpUtil import getHostByName

log = logging.getLogger("zen.MicrosoftWindows")


class ClusterNetwork(OSComponent):
    '''
    Model class for Cluster Network.
    '''
    meta_type = portal_type = 'MSClusterNetwork'

    description = None
    role = None
    state = None
    domain = ""

    _properties = OSComponent._properties + (
        {'id': 'description', 'label': 'Description', 'type': 'string'},
        {'id': 'role', 'label': 'Cluster Use', 'type': 'string'},
        {'id': 'state', 'label': 'State', 'type': 'string'},
        {'id': 'domain', 'label': 'Domain', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ('os', ToOne(ToManyCont,
            'ZenPacks.zenoss.Microsoft.Windows.OperatingSystem',
            'clusternetworks')),
    )

    def getRRDTemplateName(self):
        return 'ClusterNetwork'

InitializeClass(ClusterNetwork)
