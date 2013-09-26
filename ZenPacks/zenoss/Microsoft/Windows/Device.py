##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


import logging
log = logging.getLogger("zen.MicrosoftWindows")

from Globals import InitializeClass

from Products.ZenModel.Device import Device as BaseDevice
from Products.ZenModel.ManagedEntity import ManagedEntity
from Products.ZenModel.ZenStatus import ZenStatus

from ZenPacks.zenoss.Microsoft.Windows.OperatingSystem import OperatingSystem

from ZenPacks.zenoss.Microsoft.Windows.Hardware import Hardware


class Device(BaseDevice):
    """
    A device class that knows about enclosures
    """

    def __init__(self, id, buildRelations=True):
        ManagedEntity.__init__(self, id, buildRelations=buildRelations)

        os = OperatingSystem()
        self._setObject(os.id, os)

        hw = Hardware()
        self._setObject(hw.id, hw)

        self._lastPollSnmpUpTime = ZenStatus(0)
        self._snmpLastCollection = 0
        self._lastChange = 0

    def setErrorNotification(self, event):

        status, message = event
        if status == 'clear':
            self.dmd.ZenEventManager.sendEvent(dict(
                device=self.id,
                summary=message,
                eventClass='/Status',
                eventKey='ConnectionError',
                severity=0,
                ))

        else:
            #send event that connection failed.
            self.dmd.ZenEventManager.sendEvent(dict(
                device=self.id,
                summary=message,
                eventClass='/Status',
                eventKey='ConnectionError',
                severity=5,
                ))

            return

    def getErrorNotification(self):
        return


InitializeClass(Device)
