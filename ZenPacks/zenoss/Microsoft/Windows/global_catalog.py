##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


from Products.ZenModel.DeviceComponent import DeviceComponent
from Products.Zuul.catalog.global_catalog import IpInterfaceWrapper


class TeamInterfaceWrapper(IpInterfaceWrapper):
    def objectImplements(self):
        return super(TeamInterfaceWrapper, self).objectImplements() + [
            '%s.%s' % (DeviceComponent.__module__, DeviceComponent.__name__)]


class InterfaceWrapper(IpInterfaceWrapper):
    def objectImplements(self):
        return super(InterfaceWrapper, self).objectImplements() + [
            '%s.%s' % (DeviceComponent.__module__, DeviceComponent.__name__)]
