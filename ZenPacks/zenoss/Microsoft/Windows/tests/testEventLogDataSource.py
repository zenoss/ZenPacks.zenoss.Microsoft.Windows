#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import Globals
from mock import Mock, sentinel
import pprint

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.datasources.EventLogDataSource import EventLogPlugin
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle_file

INFO_EXPECTED = {
    'component': u'Microsoft-Windows-Winlogon',
    'computername': u'SQLSRV02.solutions-dev.local',
    'device': 'machine',
    'eventClassKey': u'Microsoft-Windows-Winlogon_6000',
    'eventGroup': sentinel.eventlog,
    'eventidentifier': u'6000',
    'message': u'The winlogon notification subscriber <AUInstallAgent> was unavailable to handle a notification event.',
    'ntevid': u'6000',
    'originaltime': u'07/13/2017 14:19:50',
    'severity': 2,
    'summary': u'The winlogon notification subscriber <AUInstallAgent> was unavailable to handle a notification event',
    'user': u''}

CRITICAL_EXPECTED = {
    'component': u'Microsoft-Windows-Kernel-Power',
    'computername': u'SQLSRV02.solutions-dev.local',
    'device': 'machine',
    'eventClassKey': 'Microsoft-Windows-Kernel-Power_41',
    'eventGroup': sentinel.eventlog,
    'eventidentifier': u'41',
    'message': u'The last sleep transition was unsuccessful. This error could be caused if the system stopped'
               ' responding, failed, or lost power during the sleep transition.',
    'ntevid': u'41',
    'originaltime': u'07/13/2017 14:20:50',
    'severity': 5,
    'summary': u'The last sleep transition was unsuccessful',
    'user': u''}


class TestDataSourcePlugin(BaseTestCase):
    def test_onSuccess(self):
        plugin = EventLogPlugin()

        results = load_pickle_file(self, 'EventLogPlugin')[0]
        config = Mock(
            id="machine",
            datasources=[Mock(params={'eventlog': sentinel.eventlog},
                              datasource='DataSource')],
        )
        res = plugin.onSuccess(results, config)
        self.maxDiff = None
        self.assertEquals(len(res['events']), 6, msg='Received {}'.format(pprint.pformat(res)))
        self.assertEquals(res['events'][0], INFO_EXPECTED)
        self.assertEquals(res['events'][1], CRITICAL_EXPECTED)
        self.assertEquals(res['events'][2]['summary'], 'Windows EventLog: successful event collection')
        # check for invalid severity to look for new default severity
        results.stdout[1] = results.stdout[1].replace('"EntryType": "Information"', '"EntryType": "Invalid"')
        res = plugin.onSuccess(results, config)
        self.assertEquals(res['events'][0]['severity'], 2)


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestDataSourcePlugin))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
