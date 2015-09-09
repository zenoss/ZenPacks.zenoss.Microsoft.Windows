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

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.WinCluster import WinCluster


class TestProcesses(BaseTestCase):

    def setUp(self):
        self.plugin = WinCluster()
        self.device = StringAttributeObject()
        self.results = StringAttributeObject()
        self.results['nodes'] = ['node0', 'node1']
        self.results['domain'] = 'domain0'
        self.results['resources'] = ["title0|coregroup0|node0|state0|description0|id0|priority0"]
        self.results['apps'] = ["title0|title0|state0|description0|"]

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data[0].setClusterHostMachines, ['node0', 'node1'])
        self.assertEquals(data[1].maps[0].id, 'id0')
        self.assertEquals(data[1].maps[0].description, 'description0')
        self.assertEquals(data[1].maps[0].domain, 'domain0')
        self.assertEquals(data[1].maps[0].ownernode, 'node0')
        self.assertEquals(data[1].maps[0].state, 'state0')
        self.assertEquals(data[1].maps[0].title, 'title0')
