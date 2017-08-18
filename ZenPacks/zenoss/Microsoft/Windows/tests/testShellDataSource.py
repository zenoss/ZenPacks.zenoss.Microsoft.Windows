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

from ZenPacks.zenoss.Microsoft.Windows.lib.txwinrm.shell import CommandResponse
from twisted.python.failure import Failure
from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle, load_pickle_file
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import sentinel, patch, Mock

from ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource import (
    ShellDataSourcePlugin, DCDiagStrategy
)


class TestShellDataSourcePlugin(BaseTestCase):
    def setUp(self):
        self.success = load_pickle(self, 'results')
        self.config = load_pickle(self, 'config')
        self.plugin = ShellDataSourcePlugin()

    def test_onSuccess(self):
        data = self.plugin.onSuccess(self.success, self.config)
        self.assertEquals(len(data['values']), 12)
        self.assertEquals(len(data['events']), 29)
        self.assertFalse(all(e['severity'] for e in data['events']))

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.log', Mock())
    def test_onError(self):
        f = None
        try:
            f = Failure('foo')
        except TypeError:
            f = Failure()
        data = self.plugin.onError(f, sentinel)
        self.assertEquals(len(data['events']), 1)
        self.assertEquals(data['events'][0]['severity'], 3)

    def test_clean_output(self):
        strategy = DCDiagStrategy()
        strategy.run_tests = {'testFoo', 'testBar', 'testBaz'}

        inp = [u'No Such Object',
               u'......................... COMP-NAME failed test',
               u'testFoo']
        out = strategy._clean_output(inp)
        self.assertEquals(out, [inp[0], inp[1] + ' ' + inp[2]])

        inp2 = [u'Missing Expected Value',
                u'......................... COMP-NAME failed test',
                u'testBar']
        out = strategy._clean_output(inp + inp2)
        self.assertEquals(out, [inp[0], inp[1] + ' ' + inp[2],
                                inp2[0], inp2[1] + ' ' + inp2[2]])

        inp3 = [u'......................... COMP-NAME failed test testBaz']

        out = strategy._clean_output(inp + inp3)
        self.assertEquals(out, [inp[0], inp[1] + ' ' + inp[2]] + inp3)

        out = strategy._clean_output(inp3 + inp)
        self.assertEquals(out, inp3 + [inp[0], inp[1] + ' ' + inp[2]])

        out = strategy._clean_output(inp3)
        self.assertEquals(out, inp3)

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.log', Mock())
    def test_nagios_parser(self):
        # OK status from Nagios and 4 datapoints
        # OK - no errors or warnings|default_lines=10 default_warnings=0 default_criticals=0 default_unknowns=0
        win_results = load_pickle_file(self, 'ShellDataSourcePlugin_onSuccess_141718')[0]
        nagios_ok = Mock()
        nagios_ok.datasources = win_results[1]
        nagios_ok.id = nagios_ok.datasources[0].device
        data = self.plugin.onSuccess(win_results, nagios_ok)
        self.assertEquals(len(data['values'][None]), 4)
        self.assertEquals(data['values'][None]['default_criticals'], (0.0, 'N'))
        self.assertEquals(len(data['events']), 8)
        self.assertEquals(data['events'][0]['severity'], 0)
        # now test nagios with a CRITICAL return code and exit_code of 2
        # CRITICAL - (11 errors) - testing ...|default_lines=12 default_warnings=0 default_criticals=11 default_unknowns=0
        # we should see datapoints and a ZenEventClasses.Critical event
        win_results = load_pickle_file(self, 'ShellDataSourcePlugin_onSuccess_143352')[0]
        nagios_critical = Mock()
        win_results[1][0].eventClass = '/Status/Nagios/Test'
        nagios_critical.datasources = win_results[1]
        nagios_critical.id = nagios_critical.datasources[0].device
        data = self.plugin.onSuccess(win_results, nagios_critical)
        self.assertEquals(len(data['values'][None]), 4)
        self.assertEquals(data['values'][None]['default_criticals'], (11.0, 'N'))
        self.assertEquals(len(data['events']), 8)
        self.assertEquals(data['events'][0]['severity'], 5)
        self.assertEquals(data['events'][0]['eventClass'], '/Status/Nagios/Test')

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.log', Mock())
    def test_sql_no_counters(self):
        parms = load_pickle_file(self, 'ShellDataSourcePlugin_onSuccess_162846')[0]
        stdout = [u'databasename : db01',
                  u'databasestatus:Normal',
                  u'databasename:master',
                  u'databasestatus:Normal',
                  u'databasename : msdb',
                  u'databasestatus:Normal',
                  u'databasename : tempdb',
                  u'databasestatus:Normal',
                  u'databasename : model',
                  u'databasestatus:Normal']
        sql_config = Mock()
        sql_config.datasources = parms[1]
        sql_config.id = sql_config.datasources[0].device
        results = (parms[0], parms[1], CommandResponse(stdout, [], 0))
        data = self.plugin.onSuccess(results, sql_config)
        self.assertEquals(len(data['values']), 5)
        self.assertEquals(len(data['events']), 15)
        # we should see status of databases even if no counters are returned.
        for x in xrange(5):
            self.assertEquals('The database is available.', data['events'][x]['message'])
        for x in xrange(5, 10):
            self.assertEquals(
                'Error parsing data in powershell MSSQL strategy for "ActiveTransactions" datasource',
                data['events'][x]['summary'])


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestShellDataSourcePlugin))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
