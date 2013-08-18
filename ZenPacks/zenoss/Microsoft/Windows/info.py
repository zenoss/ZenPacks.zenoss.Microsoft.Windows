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
from Products.Zuul.decorators import info
from ZenPacks.zenoss.Microsoft.Windows.interfaces import IWinIISInfo, IWinServiceInfo, IWinProcInfo


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
    usermonitor = ProxyProperty('usermonitor')

    def getMonitor(self):
        monitorstatus = self._object.getMonitor()
        return monitorstatus

    def setMonitor(self, value):
        self._object.usermonitor = True
        self._object.monitor = value
        self._object.index_object()

    monitor = property(getMonitor, setMonitor)


class WinProcInfo(WinComponentInfo):
    implements(IWinProcInfo)

    caption = ProxyProperty('caption')
    numbercore = ProxyProperty('numbercore')
    status = ProxyProperty('status')
    architecture = ProxyProperty('architecture')
    clockspeed = ProxyProperty('clockspeed')

    @property
    @info
    def manufacturer(self):
        pc = self._object.productClass()
        if (pc):
            return pc.manufacturer()

    @property
    @info
    def product(self):
        return self._object.productClass()


class WinIISInfo(WinComponentInfo):
    implements(IWinIISInfo)

    sitename = ProxyProperty('sitename')
    apppool = ProxyProperty('apppool')
    caption = ProxyProperty('caption')
    status = ProxyProperty('status')
    statusname = ProxyProperty('statusname')
