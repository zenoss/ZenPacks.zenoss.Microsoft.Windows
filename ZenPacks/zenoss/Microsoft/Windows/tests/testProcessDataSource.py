##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.tests.mock import sentinel, patch
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle

from ZenPacks.zenoss.Microsoft.Windows.datasources.ProcessDataSource import ProcessDataSourcePlugin


class TestProcessDataSourcePlugin(BaseTestCase):
    def setUp(self):
        self.success = load_pickle(self, 'result.pkl')
        self.config = load_pickle(self, 'config.pkl')
        self.plugin = ProcessDataSourcePlugin()

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ProcessDataSource.LOG')
    def test_onError(self, _):
        data = self.plugin.onError(sentinel, sentinel)
        self.assertEquals(len(data['events']), 1)
        self.assertEquals(data['events'][0]['summary'], "process scan error: sentinel.value")

    def test_onSuccess(self):
        data = self.plugin.onSuccess(self.success, self.config)
        self.assertItemsEqual(
            (x['summary'] for x in data['events']),
            ('matching processes running', 'process scan successful')
        )
