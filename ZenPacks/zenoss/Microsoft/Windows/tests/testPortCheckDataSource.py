#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import Globals

from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import MagicMock, sentinel
from ZenPacks.zenoss.Microsoft.Windows.datasources.PortCheckDataSource import PortCheckDataSourcePlugin


class TestPortCheckDataSourcePlugin(BaseTestCase):
    def setUp(self):
        self.plugin = PortCheckDataSourcePlugin()
        self.config = MagicMock(
            datasources=[
                MagicMock(params=dict(ports='['
                                            '{"port": 1, "desc": "Desc"},'
                                            '{"port": 2, "desc": "Desc"}'
                                            ']'))
            ],
            manageIp=sentinel.manageIp
        )

    def test_onSuccess(self):
        self.plugin.collect(self.config)
        self.plugin.scanner = MagicMock()
        self.plugin.scanner.getSuccesses = MagicMock(return_value={sentinel.manageIp: [1]})
        self.plugin.scanner.getFailures = MagicMock(return_value={sentinel.manageIp: [[2]]})
        data = self.plugin.onSuccess(MagicMock, self.config)
        self.assertEquals(len(data['events']), 3)
        self.assertItemsEqual(
            ['Port 2 is not listening.  Desc', 'Port 1 is listening.  Desc', 'Port Check Successful'],
            [e['summary'] for e in data['events']]
        )

    def test_onError(self):
        data = self.plugin.onError(MagicMock, self.config)
        self.assertEquals(len(data['events']), 1)
        self.assertEquals(data['events'][0]['eventKey'], "WindowsPortCheckError")
        self.assertEquals(data['events'][0]['eventClass'], '/Status')


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestPortCheckDataSourcePlugin))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
