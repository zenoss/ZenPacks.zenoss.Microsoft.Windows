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
import time

from twisted.internet.defer import inlineCallbacks
from txwinrm.WinRMClient import SingleCommandClient
from twisted.python.failure import Failure
from ..txwinrm_utils import createConnectionInfo
from ..utils import SqlConnection
from zope.component import queryUtility
from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource import (
    ShellDataSourcePlugin, DCDiagStrategy, SqlConnection,
    PowershellMSSQLAlwaysOnAGStrategy, PowershellMSSQLAlwaysOnARStrategy,
    PowershellMSSQLAlwaysOnALStrategy, PowershellMSSQLAlwaysOnADBStrategy
)

from ZenPacks.zenoss.Microsoft.Windows.lib.txwinrm.shell import CommandResponse
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle, load_pickle_file
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import sentinel, patch, Mock, MagicMock
from ZenPacks.zenoss.Microsoft.Windows.tests.ms_sql_always_on_test_data import DummyAlwaysOnStrategiesResponse


CROCHET_AVAILABLE = False
try:
    import crochet
    crochet.setup()
    CROCHET_AVAILABLE = True
except ImportError, e:
    pass


class TestShellDataSourcePlugin(BaseTestCase):

    def setUp(self):
        self.success = load_pickle(self, 'results')
        self.config = load_pickle(self, 'config')
        self.plugin = ShellDataSourcePlugin()
    
    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.ShellDataSourcePlugin.start', time.mktime(time.localtime()))
    def test_onSuccess(self):
        data = self.plugin.onSuccess(self.success, self.config)
        self.assertEquals(len(data['values']), 5)
        self.assertEquals(len(data['events']), 10)
        self.assertFalse(all(e['severity'] for e in data['events']))
   
    if CROCHET_AVAILABLE:
        @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.createConnectionInfo')
        @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.SingleCommandClient')
        @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.queryUtility')
        @crochet.wait_for(timeout=5.0)
        @inlineCallbacks
        def test_collect(self, queryUtility, SingleCommandClient, createConnectionInfo):
            self.config.datasources[0].params['version'] = '2.9.3'
            self.config.datasources[0].params['strategy'] = 'powershell MSSQL Job'
            self.config.datasources[0].cycletime = 500
            createConnectionInfo.return_value._replace.return_value = 15
            queryUtility.return_value.build_command_line.return_value = ('mocked command_line', 'mocked script')
            SingleCommandClient.return_value.run_command.return_value = 'mocked data'
            yield self.plugin.collect(self.config)
            self.assertEquals('call()._replace(timeout=495)', str(createConnectionInfo.mock_calls[1]))

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

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.log', Mock())
    def test_onError_status(self):
        winrm_errors = [Exception(), Exception('foo')]
        kerberos_errors = map(Exception,
                              ['kerberos authGSSClientStep failed',
                               'Server not found in Kerberos database',
                               'kinit error getting initial credentials'])

        for err in winrm_errors:
            data = self.plugin.onError(Failure(err), self.config)
            self.assertEquals(data['events'][0]['eventClass'], '/Status')

        for err in kerberos_errors:
            data = self.plugin.onError(Failure(err), self.config)
            self.assertEquals(data['events'][0]['eventClass'], '/Status/Kerberos')

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
    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.ShellDataSourcePlugin.start', time.mktime(time.localtime()))
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
    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.ShellDataSourcePlugin.start', time.mktime(time.localtime()))
    def test_sql_no_counters(self):
        parms = load_pickle_file(self, 'ShellDataSourcePlugin_onSuccess_185726')[0]
        stdout = [u'db01 :counter: databasestatus :value: Normal',
                  u'master :counter: databasestatus :value: Normal',
                  u'msdb :counter: databasestatus :value: Normal',
                  u'tempdb :counter: databasestatus :value: Normal',
                  u'model :counter: databasestatus :value: Normal']
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
                'winrs: successful collection', data['events'][x]['summary'])

    def test_sqlConnection(self):
        sq = SqlConnection('instance', 'sqlusername@domain.com', 'sqlpassword', True, 11)
        self.assertNotIn('sqlpassword', ' '.join(sq.sqlConnection), sq.sqlConnection)


class TestAlwaysOnDatasourceStrategies(BaseTestCase):

    def setUp(self):
        self.ao_ag_strategy = PowershellMSSQLAlwaysOnAGStrategy()
        self.ao_ar_strategy = PowershellMSSQLAlwaysOnARStrategy()
        self.ao_al_strategy = PowershellMSSQLAlwaysOnALStrategy()
        self.ao_adb_strategy = PowershellMSSQLAlwaysOnADBStrategy()

        self.data_provider = DummyAlwaysOnStrategiesResponse()

    # Availability Group checks

    def check_mssql_ao_ag_maps(self, data):
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        object_map_0 = data[0]

        self.assertEqual(object_map_0.primary_recovery_health, 'Online')
        self.assertEqual(object_map_0.quorum_state, 'Normal quorum')
        self.assertEqual(object_map_0.relname, 'winsqlavailabilitygroups')
        self.assertEqual(object_map_0.id, '777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEqual(object_map_0.automated_backup_preference, 'Prefer Secondary')
        self.assertEqual(object_map_0.modname, 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityGroup')
        self.assertEqual(object_map_0.compname, 'os')
        self.assertEqual(object_map_0.title, 'TestAG1')
        self.assertEqual(object_map_0.set_winsqlinstance, 'WSC-NODE-02_SQLAON')
        self.assertEqual(object_map_0.synchronization_health, 'Healthy')
        self.assertEqual(object_map_0.health_check_timeout, 30000)

    def check_mssql_ao_ag_values(self, data):
        self.assertIsInstance(data, dict)
        self.assertEqual(len(data.keys()), 1)
        ag_values = data.get('777c50fd-348e-4686-a622-edd90a4340e1', {})

        self.assertEqual(ag_values['IsOnline'], (True, 'N'))
        self.assertEqual(ag_values['NumberOfDisconnectedReplicas'], (0, 'N'))
        self.assertEqual(ag_values['NumberOfReplicasWithUnhealthyRole'], (0, 'N'))
        self.assertEqual(ag_values['NumberOfNotSynchronizedReplicas'], (0, 'N'))
        self.assertEqual(ag_values['NumberOfNotSynchronizingReplicas'], (0, 'N'))
        self.assertEqual(ag_values['NumberOfSynchronizedSecondaryReplicas'], (1, 'N'))

    def check_mssql_ao_ag_events(self, data):
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)
        ag_event = data[1]

        self.assertEqual(ag_event['severity'], 0)
        self.assertEqual(ag_event['eventClassKey'], 'AOAvailabilityGroupPropChange synchronization_health')
        self.assertEqual(ag_event['component'], '777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEqual(ag_event['summary'], 'Synchronization Health of Availability Group TestAG1 is Healthy')
        self.assertEqual(ag_event['eventKey'], 'synchronization_health change')
        self.assertEqual(ag_event['device'], '10.88.122.130')
        self.assertEqual(ag_event['eventClass'], '/Status')

    # Availability Replica checks

    def check_mssql_ao_ar_maps(self, data):
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        object_map_1 = data[1]

        self.assertEqual(object_map_1.connection_state, 'Connected')
        self.assertEqual(object_map_1.failover_mode, 'Manual')
        self.assertEqual(object_map_1.relname, 'winsqlavailabilityreplicas')
        self.assertEqual(object_map_1.id, '106864b6-f741-4b3c-b6be-48daa15ff3d7')
        self.assertEqual(object_map_1.modname, 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityReplica')
        self.assertEqual(object_map_1.compname, 'os/winsqlavailabilitygroups/0b38a4e4-8c30-46e8-873e-7cd1b397bfc1')
        self.assertEqual(object_map_1.name, u'WSC-NODE-03\\SQLAON')
        self.assertEqual(object_map_1.title, u'WSC-NODE-03\\SQLAON')
        self.assertEqual(object_map_1.operational_state, 'Online')
        self.assertEqual(object_map_1.unigue_id, u'106864b6-f741-4b3c-b6be-48daa15ff3d7')
        self.assertEqual(object_map_1.state, 'Online')
        self.assertEqual(object_map_1.synchronization_state, 'Synchronizing')
        self.assertEqual(object_map_1.role, 'Secondary')
        self.assertEqual(object_map_1.synchronization_health, 'Healthy')
        self.assertEqual(object_map_1.availability_mode, 'Asynchronous commit')

    def check_mssql_ao_ar_events(self, data):
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 12)
        ar_event = data[5]

        self.assertEqual(ar_event['severity'], 0)
        self.assertEqual(ar_event['eventClassKey'], 'AOAvailabilityReplicaPropChange synchronization_health')
        self.assertEqual(ar_event['component'], '8974cff2-f04e-4399-96b5-1f256f632e6d')
        self.assertEqual(ar_event['summary'], 'Synchronization Health of Availability Replica WSC-NODE-03\\SQLAON is Healthy')
        self.assertEqual(ar_event['eventKey'], 'synchronization_health change')
        self.assertEqual(ar_event['device'], '10.88.122.130')
        self.assertEqual(ar_event['eventClass'], '/Status')

    # Availability Listener checks

    def check_mssql_ao_al_maps(self, data):
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        object_map_0 = data[0]

        self.assertEqual(object_map_0.modname, 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityListener')
        self.assertEqual(object_map_0.relname, 'winsqlavailabilitylisteners')
        self.assertEqual(object_map_0.compname, 'os/winsqlavailabilitygroups/777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEqual(object_map_0.name, u'TestAG1_TestAG_Listener')
        self.assertEqual(object_map_0.state, 'Online')
        self.assertEqual(object_map_0.dns_name, u'TestAG_Listener')
        self.assertEqual(object_map_0.title, u'TestAG1_TestAG_Listener')
        self.assertEqual(object_map_0.ip_address, u'10.88.123.201')
        self.assertEqual(object_map_0.id, '5869339c-942f-4ef1-b085-d9718db16cd3')

    def check_mssql_ao_al_events(self, data):
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        al_event = data[0]

        self.assertEqual(al_event['severity'], 0)
        self.assertEqual(al_event['eventClassKey'], 'AOAvailabilityListenerPropChange state')
        self.assertEqual(al_event['component'], '5869339c-942f-4ef1-b085-d9718db16cd3')
        self.assertEqual(al_event['summary'], 'State of Availability Listener TestAG1_TestAG_Listener is Online')
        self.assertEqual(al_event['eventKey'], 'state change')
        self.assertEqual(al_event['device'], '10.88.122.130')
        self.assertEqual(al_event['eventClass'], '/Status')

    # Availability Databases checks

    def check_mssql_ao_adb_maps(self, data):
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)
        object_map_1 = data[1]

        self.assertEqual(object_map_1.sync_state, 'Synchronized')
        self.assertEqual(object_map_1.modname, 'ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase')
        self.assertEqual(object_map_1.relname, 'databases')
        self.assertEqual(object_map_1.compname, 'os/winsqlinstances/WSC-NODE-02_SQLAON')
        self.assertEqual(object_map_1.suspended, False)
        self.assertEqual(object_map_1.title, 'test_alwayson_db_3')
        self.assertEqual(object_map_1.id, 'WSC-NODE-02_SQLAON7')

    def check_mssql_ao_adb_values(self, data):
        self.assertIsInstance(data, dict)
        self.assertEqual(len(data.keys()), 3)
        adb_values = data.get('WSC-NODE-02_SQLAON5', {})

        self.assertEqual(len(adb_values.keys()), 2)
        # type of individual value is tuple in format (<point-value>, <datapoint-timestamp>)
        db_active_transactions, _ = adb_values['ActiveTransactions']
        self.assertEqual(db_active_transactions, u'0')
        self.assertEqual(adb_values['status'], (8, 'N'))

    def check_mssql_ao_adb_events(self, data):
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 9)
        ag_event = data[3]

        self.assertEqual(ag_event['severity'], 0)
        self.assertEqual(ag_event['eventClassKey'], 'AOWinSQLDatabasePropChange status')
        self.assertEqual(ag_event['component'], 'WSC-NODE-02_SQLAON7')
        self.assertEqual(ag_event['summary'], 'Database Status of SQL Database test_alwayson_db_3 is Normal')
        self.assertEqual(ag_event['eventKey'], 'status change')
        self.assertEqual(ag_event['device'], '10.88.122.130')
        self.assertEqual(ag_event['eventClass'], '/Status')

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.log', Mock())
    def test_powershell_mssql_ao_ag_parse_result(self):

        config, response = self.data_provider.get_ao_ag_strategy_response()
        monitoring_results = self.ao_ag_strategy.parse_result(config, response)

        self.assertIsInstance(monitoring_results, dict)
        monitoring_results_keys = monitoring_results.keys()
        self.assertIn('maps', monitoring_results_keys)
        self.assertIn('values', monitoring_results_keys)
        self.assertIn('events', monitoring_results_keys)

        # check one arbitrary element from each category
        # 1. maps
        self.check_mssql_ao_ag_maps(monitoring_results['maps'])

        # 2. values
        self.check_mssql_ao_ag_values(monitoring_results['values'])

        # 3. events
        self.check_mssql_ao_ag_events(monitoring_results['events'])

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.log', Mock())
    def test_powershell_mssql_ao_ar_parse_result(self):

        config, response = self.data_provider.get_ao_ar_strategy_response()
        monitoring_results = self.ao_ar_strategy.parse_result(config, response)

        self.assertIsInstance(monitoring_results, dict)
        monitoring_results_keys = monitoring_results.keys()
        self.assertIn('maps', monitoring_results_keys)
        # 'values' are empty because they are collected by Perfmon datasource
        self.assertIn('events', monitoring_results_keys)

        # check one arbitrary element from each category
        # 1. maps
        self.check_mssql_ao_ar_maps(monitoring_results['maps'])

        # 2. events
        self.check_mssql_ao_ar_events(monitoring_results['events'])

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.log', Mock())
    def test_powershell_mssql_ao_al_parse_result(self):

        config, response = self.data_provider.get_ao_al_strategy_response()
        monitoring_results = self.ao_al_strategy.parse_result(config, response)

        self.assertIsInstance(monitoring_results, dict)
        monitoring_results_keys = monitoring_results.keys()
        self.assertIn('maps', monitoring_results_keys)
        # 'values' are empty because no datapoints are collected for Availability Listener
        self.assertIn('events', monitoring_results_keys)

        # check one arbitrary element from each category
        # 1. maps
        self.check_mssql_ao_al_maps(monitoring_results['maps'])

        # 2. events
        self.check_mssql_ao_al_events(monitoring_results['events'])

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.log', Mock())
    def test_powershell_mssql_ao_adb_parse_result(self):

        config, response = self.data_provider.get_ao_adb_strategy_response()
        monitoring_results = self.ao_adb_strategy.parse_result(config, response)

        self.assertIsInstance(monitoring_results, dict)
        monitoring_results_keys = monitoring_results.keys()
        self.assertIn('maps', monitoring_results_keys)
        self.assertIn('values', monitoring_results_keys)
        self.assertIn('events', monitoring_results_keys)

        # check one arbitrary element from each category
        # 1. maps
        self.check_mssql_ao_adb_maps(monitoring_results['maps'])

        # 2. values
        self.check_mssql_ao_adb_values(monitoring_results['values'])

        # 3. events
        self.check_mssql_ao_adb_events(monitoring_results['events'])


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestShellDataSourcePlugin))
    suite.addTest(makeSuite(TestAlwaysOnDatasourceStrategies))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
