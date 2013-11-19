##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Utilities that may cause Zope stuff to be imported.
'''

from Products.ZenModel.Device import Device
from Products.ZenModel.DeviceHW import DeviceHW
from Products.ZenModel.ManagedEntity import ManagedEntity
from Products.ZenModel.ZenStatus import ZenStatus

from ZenPacks.zenoss.Microsoft.Windows.OperatingSystem import OperatingSystem


class BaseDevice(Device):
    '''
    Provides common functionality for Device and ClusterDevice.
    '''

    def __init__(self, id, buildRelations=True):
        '''
        Initialize a new device.

        Overridden so that the os property can be created as subclass
        of the standard OperatingSystem class.
        '''
        ManagedEntity.__init__(self, id, buildRelations=buildRelations)

        os = OperatingSystem()
        self._setObject(os.id, os)

        hw = DeviceHW()
        self._setObject(hw.id, hw)

        self._lastPollSnmpUpTime = ZenStatus(0)
        self._snmpLastCollection = 0
        self._lastChange = 0

        if hasattr(self, '_create_componentSearch'):
            self._create_componentSearch()
