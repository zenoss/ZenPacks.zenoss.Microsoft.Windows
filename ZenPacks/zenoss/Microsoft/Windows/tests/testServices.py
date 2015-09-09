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

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.Services import Services


class TestProcesses(BaseTestCase):

    def setUp(self):
        self.plugin = Services()
        self.results = Mock()
        self.results.get.return_value = [StringAttributeObject()]
        self.device = StringAttributeObject()

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data.maps[0].account, 'StartName')
        self.assertEquals(data.maps[0].caption, 'Caption')
        self.assertEquals(data.maps[0].description, 'Description')
        self.assertEquals(data.maps[0].id, 'Name')
        self.assertEquals(data.maps[0].servicename, 'Name')
        self.assertEquals(data.maps[0].startmode, 'StartMode')
        self.assertEquals(data.maps[0].title, 'Caption')
