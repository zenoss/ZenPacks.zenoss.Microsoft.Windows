##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from mock import Mock

from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.IIS import IIS


class TestIIS(BaseTestCase):
    def setUp(self):
        self.plugin = IIS()

    def test_process(self):
        results = Mock(get=lambda *_: [StringAttributeObject()])
        data = self.plugin.process(StringAttributeObject(), results, Mock())
        self.assertEquals(len(data.maps), 1)
        self.assertEquals(data.maps[0].iis_version, 6)
        self.assertEquals(data.maps[0].sitename, "ServerComment")
        self.assertEquals(data.maps[0].status, "Running")
        self.assertEquals(data.maps[0].statusname, "Name")
        self.assertEquals(data.maps[0].title, "ServerComment")
