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
from twisted.python.failure import Failure
from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.tests.mock import sentinel, patch, Mock
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle

from ZenPacks.zenoss.Microsoft.Windows.datasources.ProcessDataSource import ProcessDataSourcePlugin


class TestProcessDataSourcePlugin(BaseTestCase):
    def setUp(self):
        self.success = load_pickle(self, 'result')
        self.config = load_pickle(self, 'config')
        self.plugin = ProcessDataSourcePlugin()

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ProcessDataSource.LOG', Mock())
    def test_onError(self):
        f = None
        try:
            f = Failure('process datasource error')
            msg = 'process scan error: process datasource error'
        except TypeError:
            f = Failure()
            msg = 'process scan error: Strings are not supported by Failure'
        data = self.plugin.onError(f, sentinel)
        self.assertEquals(len(data['events']), 1)
        self.assertEquals(data['events'][0]['summary'], msg)

    def test_onSuccess(self):
        data = self.plugin.onSuccess(self.success, self.config)
        self.assertItemsEqual(
            (x['summary'] for x in data['events']),
            (
                'matching processes running', 'process scan successful',
                'Authentication Successful', 'No Kerberos failures'
            )
        )
        self.assertEquals(data['events'][1]['eventClass'], '/Status')
        self.assertEquals(data['events'][1]['eventKey'], 'ProcessScanStatus')
        self.success.pop(self.success.keys()[0])
        try:
            self.plugin.onSuccess(self.success, self.config)
        except Exception as e:
            self.assertEquals(e.message, 'Received no results for Win32_Process WMI query.')


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestProcessDataSourcePlugin))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
