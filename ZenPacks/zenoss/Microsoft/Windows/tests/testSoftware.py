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

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.Software import Software


class TestProcesses(BaseTestCase):
    def setUp(self):
        self.plugin = Software()
        self.results = dict(software=Mock(stdout=['DisplayName=;InstallDate=;Vendor=|',
                                                  'DisplayName=Soft x86 - 1.0.0;'
                                                  'InstallDate=19700101;'
                                                  'Vendor=Sunway Systems|',
                                                  ]))

        self.device = StringAttributeObject()

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data.maps[0].id, 'Soft x86 - 1.0.0')
        self.assertEquals(data.maps[0].setInstallDate, '1970/01/01 00:00:00')
        self.assertTupleEqual(data.maps[0].setProductKey.args, ('Soft x86 - 1.0.0', 'Sunway Systems'))
