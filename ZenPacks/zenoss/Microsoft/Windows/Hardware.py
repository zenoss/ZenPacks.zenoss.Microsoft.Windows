##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


from Globals import InitializeClass

from Products.ZenModel.DeviceHW import DeviceHW
from Products.ZenRelations.RelSchema import ToManyCont, ToOne


class Hardware(DeviceHW):
    """
    A hardware component for Microsoft Windows.
    """
    portal_type = meta_type = "Hardware"

    _relations = DeviceHW._relations + (
        ("winrmproc", ToManyCont(ToOne,
         "ZenPacks.zenoss.Microsoft.Windows.WinProc",
          "hw")),
    )

InitializeClass(Hardware)
