##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Globals import InitializeClass
import logging

from Products.ZenModel.OSComponent import OSComponent
from Products.ZenRelations.RelSchema import ToOne, ToManyCont

log = logging.getLogger("zen.MicrosoftWindows")


class ClusterInterface(OSComponent):
    '''
    Model class for Cluster Interface.
    '''
    meta_type = portal_type = 'MSClusterInterface'

    node = None
    network = None
    ipaddresses = None
    adapter = None
    state = None
    domain = ""

    _properties = OSComponent._properties + (
        {'id': 'node', 'label': 'Node', 'type': 'string'},
        {'id': 'network', 'label': 'Network', 'type': 'string'},
        {'id': 'ipaddresses', 'label': 'IP Addresses', 'type': 'string'},
        {'id': 'adapter', 'label': 'Adapter', 'type': 'string'},
        {'id': 'state', 'label': 'State', 'type': 'string'},
        {'id': 'domain', 'label': 'Domain', 'type': 'string'},
        )

    _relations = OSComponent._relations + (
        ("clusternode", ToOne(ToManyCont,
         "ZenPacks.zenoss.Microsoft.Windows.ClusterNode", "clusterinterfaces")),
    )

    def getRRDTemplateName(self):
        return 'ClusterInterface'

    def getIconPath(self):
        '''
        Return the path to an icon for this component.
        '''
        return '/++resource++mswindows/img/Interface.png'

    def getState(self):
        try:
            state = int(self.cacheRRDValue('state', None))
        except Exception:
            return 'Unknown'

        return state

InitializeClass(ClusterInterface)
