##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
 
from Globals import InitializeClass
 
from Products.ZenRelations.RelSchema import ToOne, ToManyCont
from Products.ZenModel.OperatingSystem import OperatingSystem as BaseOS
  
  
class OperatingSystem(BaseOS):
    '''
        Provides common functionality for OperatingSystem
    '''
    _relations = BaseOS._relations + (
        ("winrmservices", ToManyCont(ToOne,
         "ZenPacks.zenoss.Microsoft.Windows.WinService",
          "os")),
        ("winrmiis", ToManyCont(ToOne,
         "ZenPacks.zenoss.Microsoft.Windows.WinIIS",
          "os")),
        ("winsqlinstances", ToManyCont(ToOne,
         "ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance",
          "os")),
        ("clusterservices", ToManyCont(ToOne,
         "ZenPacks.zenoss.Microsoft.Windows.ClusterService",
          "os")),
        ("clusternodes", ToManyCont(ToOne,
         "ZenPacks.zenoss.Microsoft.Windows.ClusterNode",
         "os")),
        ("clusternetworks", ToManyCont(ToOne,
         "ZenPacks.zenoss.Microsoft.Windows.ClusterNetwork",
         "os")),
        )

InitializeClass(OperatingSystem)
