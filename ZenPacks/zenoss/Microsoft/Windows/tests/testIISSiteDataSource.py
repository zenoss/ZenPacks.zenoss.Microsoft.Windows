#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import Globals  # noqa
import pprint
from twisted.python.failure import Failure
from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import MagicMock, sentinel
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle_file

from ZenPacks.zenoss.Microsoft.Windows.datasources.IISSiteDataSource import IISSiteDataSourcePlugin


class TestIISSiteDataSourcePlugin(BaseTestCase):
    def setUp(self):
        self.plugin = IISSiteDataSourcePlugin()
        super(TestIISSiteDataSourcePlugin, self).setUp()

    def test_onSuccess(self):
        results = load_pickle_file(self, 'IISSiteDataSourcePlugin_onSuccess_162344')[0]
        data = self.plugin.onSuccess(results, MagicMock(
            id="windows_test",
            datasources=[MagicMock(datasource='IISSiteDataSource',
                                   params={'eventlog': sentinel.eventlog,
                                           'statusname': 'Default Web Site',
                                           'iis_version': u'8.5',
                                           'apppool': 'defaultapppool'})],
        ))
        self.assertEquals(len(data['events']), 5, msg='Expected 5 events: {}'.format(pprint.pformat(data['events'])))
        self.assertEquals("Monitoring ok", data['events'][2]['summary'])
        self.assertIn("is in Running state", data['events'][0]['summary'])
        self.assertIn("is in Running state", data['events'][1]['summary'])
        self.assertEquals(data['values'][data['values'].keys()[0]]['status'], (0, 'N'))
        self.assertEquals(data['values'][data['values'].keys()[0]]['appPoolState'], (3, 'N'))

    def test_onError(self):
        f = None
        try:
            f = Failure('foo')
        except TypeError:
            f = Failure()
        data = self.plugin.onError(f, MagicMock(
            id=sentinel.id,
            datasources=[MagicMock(params={'eventlog': sentinel.eventlog})],
        ))
        self.assertEquals(len(data['events']), 1)
        self.assertEquals(data['events'][0]['device'], sentinel.id)
        self.assertIn("IISSite: Failed collection", data['events'][0]['summary'])

    def test_onError_status(self):
        winrm_errors = [Exception(), Exception('foo')]
        kerberos_errors = map(Exception,
                              ['kerberos authGSSClientStep failed',
                               'Server not found in Kerberos database',
                               'kinit error getting initial credentials'])

        config = MagicMock(
            id='127.0.0.1',
            datasources=[MagicMock(params={'eventlog': sentinel.eventlog})],
        )

        for err in winrm_errors:
            data = self.plugin.onError(Failure(err), config)
            self.assertEquals(data['events'][0]['eventClass'], '/Status')

        for err in kerberos_errors:
            data = self.plugin.onError(Failure(err), config)
            self.assertEquals(data['events'][0]['eventClass'],
                              '/Status/Kerberos')


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestIISSiteDataSourcePlugin))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
