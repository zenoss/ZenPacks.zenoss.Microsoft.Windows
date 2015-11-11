##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from mock import Mock, sentinel

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.datasources.EventLogDataSource import EventLogPlugin


class TestDataSourcePlugin(BaseTestCase):
    def test_onSuccess(self):
        plugin = EventLogPlugin()

        res = plugin.onSuccess([
            {'Category': u'(0)',
             'EntryType': u'Information',
             'EventID': u'10120',
             'InstanceId': u'468872',
             'MachineName': u'machine',
             'Message': sentinel.message,
             'Source': u'WinRM',
             'TimeGenerated': u'05/30/2014 18:27:22',
             'UserName': u''}
        ], Mock(
            id=sentinel.id,
            datasources=[Mock(params={'eventlog': sentinel.eventlog})],
        ))

        self.assertEquals(len(res['events']), 2)
        self.assertEquals(res['events'][0]['summary'], sentinel.message)
        self.assertEquals(res['events'][0]['eventGroup'], sentinel.eventlog)


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestDataSourcePlugin))
    return suite
