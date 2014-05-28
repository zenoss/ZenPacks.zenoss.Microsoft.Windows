##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from mock import Mock, sentinel

from Products.ZenEvents import ZenEventClasses
from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.datasources.EventLogDataSource import EventLogPlugin

class TestDataSourcePlugin(BaseTestCase):
    def test_onSuccess(self):
        plugin = EventLogPlugin()

        res = plugin.onSuccess([
            {'severity': 'SuccessAudit', 'message': 'test'},
        ], Mock(id=sentinel.id))

        expectation = plugin.new_data()
        expectation['events'] = [
            {'device': sentinel.id,
             'eventClassKey': 'WindowsEventLog',
             'eventKey': 'WindowsEvent',
             'severity': ZenEventClasses.Info,
             'summary': 'Collected Event: test'},
            {'device': sentinel.id,
             'eventClassKey': 'WindowsEventLogSuccess',
             'eventKey': 'WindowsEventCollection',
             'severity': ZenEventClasses.Clear,
             'summary': 'Windows EventLog: successful event collection'},
        ]
        self.assertEquals(res, expectation)

def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestDataSourcePlugin))
    return suite
