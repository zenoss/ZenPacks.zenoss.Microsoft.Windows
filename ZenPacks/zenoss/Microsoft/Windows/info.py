##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from zope.interface import implements

from Products.Zuul.infos import ProxyProperty
from Products.Zuul.infos.component import ComponentInfo

from ZenPacks.zenoss.Microsoft.Windows.interfaces import *


class WinComponentInfo(ComponentInfo):
    title = ProxyProperty('title')


class WinServiceInfo(WinComponentInfo):
    implements(IWinServiceInfo)

    servicename = ProxyProperty('servicename')
    caption = ProxyProperty('caption')
    description = ProxyProperty('description')
    startmode = ProxyProperty('startmode')
    account = ProxyProperty('account')
    state = ProxyProperty('state')


class WinProcInfo(WinComponentInfo):
    implements(IWinProcInfo)

    caption = ProxyProperty('caption')
    numbercore = ProxyProperty('numbercore')
    status = ProxyProperty('status')
    architecture = ProxyProperty('architecture')
    clockspeed = ProxyProperty('clockspeed')


class WinIISInfo(WinComponentInfo):
    implements(IWinIISInfo)

    sitename = ProxyProperty('sitename')
    apppool = ProxyProperty('apppool')
    caption = ProxyProperty('caption')
