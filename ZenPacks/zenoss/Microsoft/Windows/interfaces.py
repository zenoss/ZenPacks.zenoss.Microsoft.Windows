##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from . import schema

from Products.Zuul.form import schema as form_schema
import Products.Zuul.interfaces.component as zuul
from Products.Zuul.utils import ZuulMessageFactory as _t


class IInterfaceInfo(schema.IInterfaceInfo, zuul.IIpInterfaceInfo):
    """
    Info adapter for Interface components.
    """


class IWinServiceInfo(schema.IWinServiceInfo, zuul.IWinServiceInfo):
    """
    Info adapter for WinService components.
    """
    usermonitor = form_schema.Bool(title=_t(u'Manually Selected Monitor State.'
                                            '  This does not enable/disable monitoring.'),
                                   alwaysEditable=True)
