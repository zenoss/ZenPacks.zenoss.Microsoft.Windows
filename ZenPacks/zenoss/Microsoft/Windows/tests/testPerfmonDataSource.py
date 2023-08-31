#!/usr/bin/env python
# coding=utf-8

##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import Globals
from itertools import repeat
from collections import namedtuple

from twisted.internet.defer import inlineCallbacks

from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import sentinel, patch, Mock
from ZenPacks.zenoss.Microsoft.Windows.datasources.PerfmonDataSource import (
    format_stdout,
    format_counters,
    DataPersister,
    counter_returned,
    PerfmonDataSourcePlugin,
    Failure,
    RequestError
)
from ZenPacks.zenoss.Microsoft.Windows.lib.txwinrm.shell import CommandResponse

STDOUT = '''  Timestamp                 CounterSamples
  ---------                 --------------
  2/28/2018 10:28:06 PM     \\sqlsrv02\memory\available bytes :
  2736390144
'''


class DataSource(namedtuple('DataSource', ['plugin_classname', 'datasource'])):
    pass


class Config(namedtuple('Config', ['id'])):
    pass


class TestDataPersister(BaseTestCase):
    def setUp(self):
        self.dp = DataPersister()
        self.dp.touch(sentinel.device0)

    def test_maintenance(self):
        self.dp.devices[sentinel.device0]['last'] = 0
        self.dp.maintenance()
        self.assertEquals(len(self.dp.devices), 0)

    def test_touch(self):
        for _ in repeat(None, 2):
            self.dp.touch(sentinel.device1)
            self.assertEquals(len(self.dp.devices), 2)

    def test_get(self):
        device = self.dp.get(sentinel.device0)
        self.assertEquals(device['maps'], [])

    def test_get_events(self):
        events = self.dp.get_events(sentinel.device0)
        self.assertEquals(len(events), 0)

    def test_remove(self):
        self.dp.remove(sentinel.device0)
        self.assertEquals(len(self.dp.devices), 0)

    def test_add_event(self):
        event0 = {
            'device': 'device',
            'eventClass': '/Status/Winrm',
            'eventKey': 'Windows Perfmon Collection Error',
            'severity': 3,
            'summary': 'errorMessage',
            'ipAddress': '10.10.10.10'}
        datasources = DataSource('ZenPacks.zenoss.Microsoft.Windows.datasources.PerfmonDataSource',
                                 'test_add_event')
        self.dp.add_event(sentinel.device0, [datasources], event0)
        self.assertEquals(len(self.dp.devices[sentinel.device0]['events']), 1)

    def test_add_value(self):
        self.dp.add_value(sentinel.device0,
                          sentinel.component0,
                          sentinel.datasource0,
                          sentinel.value0,
                          sentinel.collect_time0)
        self.assertEquals(self.dp.devices[sentinel.device0]['values']
                          [sentinel.component0][sentinel.datasource0],
                          (sentinel.value0, sentinel.collect_time0))

    def test_pop(self):
        d0 = self.dp.pop(sentinel.device0)
        self.assertEquals(d0['maps'], [])
        self.assertEquals(len(self.dp.devices), 0)


class TestFormat_counters(BaseTestCase):
    def test_format_counters(self):
        self.assertEquals(format_counters(['a', 'b']), "('a'),('b')")
        self.assertEquals(format_counters(["\Système\Temps d’activité système"]), "('\Système\Temps d'+[char]8217+'activité système')")


class TestFormat_stdout(BaseTestCase):
    def test_format_stdout(self):
        self.assertEquals(format_stdout([]), ([], False))
        self.assertEquals(format_stdout(["Readings : "]), ([""], True))


class TestCounterReturned(BaseTestCase):
    def test_counter_returned(self):
        result = CommandResponse(STDOUT.split('\n'), [], 0)
        self.assertTrue(counter_returned(result))
        result = CommandResponse([], ['some sort of error'], 1)
        self.assertFalse(counter_returned(result))


def dummy_generateClearAuthEvents(config, events):
    pass


class TestPerfmonDataSourcePlugin(BaseTestCase):

    def plugin_simplified_init(datasource, config):
        datasource.config = config
        datasource.unique_id = 'test_unigue_id'
        datasource.commandlines = 'test_command_line'
        datasource._start_counter = 0
        datasource.network_failures = 0
        datasource.retry_count = 0
        datasource.was_receive_count = 0  # a new property to track how many tomes 'receive' method was called

    def plugin_modified_receive(datasource):
        datasource.was_receive_count += 1

    def plugin_modified_reset(datasource):
        pass

    def plugin_modified_stop(datasource):
        pass

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.PerfmonDataSource.LOG', Mock())
    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.PerfmonDataSource.PerfmonDataSourcePlugin.__init__', plugin_simplified_init)
    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.PerfmonDataSource.PerfmonDataSourcePlugin.receive', plugin_modified_receive)
    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.PerfmonDataSource.PerfmonDataSourcePlugin.reset', plugin_modified_reset)
    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.PerfmonDataSource.PerfmonDataSourcePlugin.stop', plugin_modified_stop)
    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.PerfmonDataSource.generateClearAuthEvents', dummy_generateClearAuthEvents)
    def test_onReceiveFail(self):
        config = Config('test_config_id')
        plugin = PerfmonDataSourcePlugin(config)

        error_messages_500_code = ('HTTP status: 500. Class not registered',
                                   'HTTP status: 500. Illegal operation attempted on a registry key that has been marked for deletion')

        for error_msg in error_messages_500_code:
            # reset 'retry_count' and 'was_receive_count' before each test step
            plugin.retry_count = 0
            plugin.was_receive_count = 0

            failure = Failure(RequestError(error_msg))
            plugin.onReceiveFail(failure)
            self.assertEquals(plugin.retry_count, 1)
            self.assertEquals(plugin.was_receive_count, 1)


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestFormat_stdout))
    suite.addTest(makeSuite(TestFormat_counters))
    suite.addTest(makeSuite(TestDataPersister))
    suite.addTest(makeSuite(TestCounterReturned))
    suite.addTest(makeSuite(TestCounterReturned))
    suite.addTest(makeSuite(TestPerfmonDataSourcePlugin))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
