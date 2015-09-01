##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from mock import Mock, sentinel, patch

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.CPUs import CPUs


class MockProcessor(object):
    SocketDesignation = '01'

    def __init__(self):
        for i in ('Name', 'Version', 'Description', 'DeviceID'):
            setattr(self, i, str(i))

    def __getattr__(self, _):
        return 1


class TestCPUs(BaseTestCase):
    def setUp(self):
        self.results = dict(
            Win32_CacheMemory=[Mock(DeviceID='Cache Memory 0', InstalledSize=1)],
            Win32_Processor=[MockProcessor()]
        )

    def test_process(self):
        m = CPUs().process(sentinel, self.results, Mock()).maps[0]
        for i in ('cacheSizeL1', 'cacheSizeL2', 'cacheSizeL3', 'cacheSpeedL2', 'cacheSpeedL3',
                  'clockspeed', 'cores', 'extspeed', 'socket', 'threads'):
            self.assertEquals(getattr(m, i), 1)
        self.assertEquals(m.description, 'Description')
        self.assertEquals(m.id, 'DeviceID')
        self.assertEquals(m.title, 'Name')
