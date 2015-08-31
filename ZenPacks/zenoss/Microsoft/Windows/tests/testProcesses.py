##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.Processes import Processes


class TestProcesses(BaseTestCase):

    def setUp(self):
        self.plugin = Processes()
        self.device = load_pickle(self, 'device')
        self.results = load_pickle(self, 'results')

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(len(data.maps), 15)
        for i in data.maps:
            self.assertTrue(i.supports_WorkingSetPrivate)
            self.assertTrue(i.id.startswith('zport_dmd_Processes_Zenoss_osProcessClasses_WIN_'))
            self.assertEquals(i.setOSProcessClass, '/Processes/Zenoss/osProcessClasses/WIN')
            self.assertEquals(i.displayName, i.monitoredProcesses[0])
