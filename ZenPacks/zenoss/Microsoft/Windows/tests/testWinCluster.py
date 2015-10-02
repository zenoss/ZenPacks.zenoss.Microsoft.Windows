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
        self.results['nodes_data'] = ['node0|1|1|2|state0']
        self.results['clusterdisk'] = ['2beb|disk1|Vol{2beb}|node0|1|1|2147199|1937045|Online']
        self.results['clusternetworks'] = ['e4a2|Network1||Up']
        self.results['nodeinterfaces'] = ['cffc|node0-Ethernet|node0|Network1|127.0.0.1|Intel(R)|Up']
        self.results['csv'] = ['29df|CSV Disk|Volume1|node0|2|1|10734268|10672029|Online']
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
        self.assertEquals(data[4].maps[0].id, '2beb')
        self.assertEquals(data[4].maps[0].freespace, '1.85MB')
        self.assertEquals(data[4].maps[0].size, '2.05MB')
        self.assertEquals(data[4].maps[0].ownernode, 'node0')
        self.assertEquals(data[4].maps[0].partitionnumber, '1')
        self.assertEquals(data[4].maps[0].disknumber, '1')
        self.assertEquals(data[4].maps[0].domain, 'domain0')
        self.assertEquals(data[4].maps[0].title, 'disk1')
        self.assertEquals(data[4].maps[0].volumepath, 'Vol{2beb}')
        self.assertEquals(data[4].maps[0].state, 'Online')
