##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from . import schema

from Products.Zuul.form import schema as form_schema
import Products.Zuul.interfaces.component as zuul
from Products.Zuul.utils import ZuulMessageFactory as _t


class IFileSystemInfo(schema.IFileSystemInfo, zuul.IFileSystemInfo):
    """
    Info adapter for FileSystem components.
    """


class ICPUInfo(schema.ICPUInfo, zuul.ICPUInfo):
    """
    Info adapter for CPU components.
    """


class IOSProcessInfo(schema.IOSProcessInfo, zuul.IOSProcessInfo):
    """
    Info adapter for OSProcess components.
    """


class IInterfaceInfo(schema.IInterfaceInfo, zuul.IIpInterfaceInfo):
    """
    Info adapter for Interface components.
    """


class IWinServiceInfo(zuul.IWinServiceInfo):
    """
    Info adapter for WinService components.
    """
    formatted_description = form_schema.TextLine(title=_t(u'Description'), readonly=True)
    usermonitor = form_schema.Bool(title=_t(u'Manually Selected Monitor State'),
                                   alwaysEditable=True)
