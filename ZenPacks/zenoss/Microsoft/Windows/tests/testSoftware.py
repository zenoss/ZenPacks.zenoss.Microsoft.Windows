#!/usr/bin/env python
# coding=utf-8

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
                                                  'DisplayName=?????????? Microsoft Report Viewer ??? Visual Studio 2013;'
                                                  'InstallDate=20150710;Vendor=Microsoft Corporation |',
                                                  'DisplayName=Visual Studio 2013? Microsoft Report Viewer ?? ??;'
                                                  'InstallDate=20150710;Vendor=Microsoft Corporation |',
                                                  'DisplayName=Soft x86 - 1.0.0;'
                                                  'InstallDate=19700101;'
                                                  'Vendor=Sunway Systems|',
                                                  'DisplayName=Soft x86 - 1.0.0;'
                                                  'InstallDate=19700101;'
                                                  'Vendor=Вендор|',
                                                  'DisplayName=;xxx;yyy|',
                                                  'DisplayName=Software;InstallDate=;Vendor=SoftCorp'
                                                  ]))

        self.device = StringAttributeObject()

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data.maps[0].id, 'Microsoft Report Viewer _ Visual Studio 2013')
        self.assertEquals(data.maps[0].setProductKey.args, ('Microsoft Report Viewer _ Visual Studio 2013', 'Microsoft Corporation'))
        self.assertEquals(data.maps[1].id, 'Visual Studio 2013_ Microsoft Report Viewer')
        self.assertEquals(data.maps[1].setProductKey.args, ('Visual Studio 2013_ Microsoft Report Viewer', 'Microsoft Corporation'))
        self.assertEquals(data.maps[2].id, 'Soft x86 - 1.0.0')
        self.assertEquals(data.maps[2].setInstallDate, '1970/01/01 00:00:00')
        self.assertTupleEqual(data.maps[2].setProductKey.args, ('Soft x86 - 1.0.0', 'Sunway Systems'))
        self.assertTupleEqual(data.maps[3].setProductKey.args, ('Soft x86 - 1.0.0', 'Unknown'))
        self.assertFalse(hasattr(data.maps[4], 'setInstallDate'))
        self.assertEquals(len(data.maps), 5)


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestProcesses))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
