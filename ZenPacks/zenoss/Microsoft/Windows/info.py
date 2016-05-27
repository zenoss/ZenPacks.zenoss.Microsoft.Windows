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

from . import schema
from ZenPacks.zenoss.Microsoft.Windows.interfaces import *


class FileSystemInfo(schema.FileSystemInfo, FileSystemInfo):
    implements(IFileSystemInfo)

class CPUInfo(schema.CPUInfo, CPUInfo):
    implements(ICPUInfo)

class OSProcessInfo(schema.CPUInfo, OSProcessInfo):
    implements(IOSProcessInfo)

class InterfaceInfo(schema.InterfaceInfo, IpInterfaceInfo):
    implements(IInterfaceInfo)

