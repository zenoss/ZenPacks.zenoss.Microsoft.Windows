#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import Globals
from mock import Mock

from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.IIS import IIS
from ZenPacks.zenoss.Microsoft.Windows.lib.txwinrm.shell import CommandResponse


class TestIIS(BaseTestCase):
    def setUp(self):
        self.plugin = IIS()

    def test_process(self):
        results = Mock(get=lambda *_: [StringAttributeObject()])
        data = self.plugin.process(StringAttributeObject(), results, Mock())
        self.assertEquals(len(data), 2)
        self.assertEquals(len(data[1].maps), 1)
        self.assertEquals(data[1].maps[0].iis_version, 6)
        self.assertEquals(data[1].maps[0].sitename, "ServerComment")
        self.assertEquals(data[1].maps[0].statusname, "Name")
        self.assertEquals(data[1].maps[0].title, "ServerComment")

        # test if no iis sites returned, probably means iis not installed
        # and we need to set is_iis to False so IIS template is not used
        data = self.plugin.process(StringAttributeObject(), {'version': CommandResponse([], [], 0)}, Mock())
        self.assertFalse(data[0].is_iis)


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestIIS))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
