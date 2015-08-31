##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.Routes import Routes


class TestProcesses(BaseTestCase):

    def setUp(self):
        self.plugin = Routes()
        self.device = StringAttributeObject()

        result = StringAttributeObject()
        result.Mask = '255.255.255.0'
        result.Protocol = 2
        result.Type = 4

        self.results = StringAttributeObject()
        self.results.Win32_IP4RouteTable = [result]

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data.maps[0].id, 'Destination_24')
        self.assertEquals(data.maps[0].routemask, 24)
        self.assertEquals(data.maps[0].routeproto, 'local')
        self.assertEquals(data.maps[0].routetype, 'indirect')
        self.assertEquals(data.maps[0].setInterfaceIndex, 'InterfaceIndex')
        self.assertEquals(data.maps[0].setNextHopIp, 'NextHop')
        self.assertEquals(data.maps[0].setTarget, data.maps[0].title, 'Destination/24')
        for i in range(1, 5):
            self.assertEquals(getattr(data.maps[0], 'metric%d' % i), 'Metric%d' % i)
