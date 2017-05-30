##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Globals import InitializeClass

from Products.ZenModel.OperatingSystem import OperatingSystem as BaseOS


class OperatingSystem(BaseOS):
    """For relationships"""
    pass


InitializeClass(OperatingSystem)
