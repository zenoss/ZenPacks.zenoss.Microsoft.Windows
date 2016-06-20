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


class TestServices(BaseTestCase):

    def setUp(self):
        self.plugin = Services()
        self.results = Mock()
        self.results.get.return_value = [StringAttributeObject()]
        self.device = StringAttributeObject()

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        # getting second relationshipmap since first contains empty winservices
        rm = data[1]
        maps = rm.maps[0]
        self.assertEquals(maps.caption, 'Caption')
        self.assertEquals(maps.id, 'Name')
        self.assertEquals(maps.pathName, 'PathName')
        self.assertEquals(maps.serviceName, 'Name')
        self.assertEquals(maps.serviceType, 'ServiceType')
        self.assertEquals(maps.setServiceClass, {'description': 'Caption', 'name': 'Name'})
        self.assertEquals(maps.startMode, 'StartMode')
