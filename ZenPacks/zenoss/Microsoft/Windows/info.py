##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from zope.interface import implements
from Products.Zuul.infos.component.filesystem import FileSystemInfo
from Products.Zuul.infos.component.cpu import CPUInfo
from Products.Zuul.infos.component.osprocess import OSProcessInfo
from Products.Zuul.infos.component.ipinterface import IpInterfaceInfo
from Products.Zuul.infos.component.winservice import WinServiceInfo
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.decorators import info

from . import schema
from ZenPacks.zenoss.Microsoft.Windows.interfaces import (
    IFileSystemInfo,
    ICPUInfo,
    IOSProcessInfo,
    IInterfaceInfo,
    IWinServiceInfo)


class FileSystemInfo(schema.FileSystemInfo, FileSystemInfo):
    implements(IFileSystemInfo)


class CPUInfo(schema.CPUInfo, CPUInfo):
    implements(ICPUInfo)


class OSProcessInfo(schema.OSProcessInfo, OSProcessInfo):
    implements(IOSProcessInfo)


class InterfaceInfo(schema.InterfaceInfo, IpInterfaceInfo):
    implements(IInterfaceInfo)


class WinServiceInfo(WinServiceInfo):
    implements(IWinServiceInfo)

    usermonitor = ProxyProperty('usermonitor')

    @property
    @info
    def formatted_description(self):
        return '<div style="white-space: normal;">{}</div>'.format(
            self._object.description)

    def getMonitor(self):
        monitorstatus = self._object.monitored()
        return monitorstatus

    def setMonitor(self, value):
        self._object.usermonitor = True
        self._object.monitor = value
        self._object.index_object()

    monitor = property(getMonitor, setMonitor)
