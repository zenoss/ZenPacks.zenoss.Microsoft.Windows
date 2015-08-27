# ##############################################################################
# #
# # Copyright (C) Zenoss, Inc. 2015, all rights reserved.
# #
# # This content is made available according to terms specified in
# # License.zenoss under the directory where your Zenoss product is installed.
# #
# ##############################################################################
#

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import sentinel, patch, Mock

from ZenPacks.zenoss.Microsoft.Windows.datasources.ServiceDataSource import ServicePlugin


class TestServiceDataSourcePlugin(BaseTestCase):
    def setUp(self):
        self.success = load_pickle(self, 'results.pkl')
        self.config = load_pickle(self, 'config.pkl')
        self.plugin = ServicePlugin()

    def test_onSuccess(self):
        data = self.plugin.onSuccess(self.success, self.config)
        self.assertEquals(len(data['events']), 2)
        self.assertEquals(data['events'][0]['summary'],
                          'Service Alert: aspnet_state has changed to Stopped state')
        self.assertEquals(data['events'][1]['summary'],
                          'Windows Service Check: successful service collection')

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ServiceDataSource.log', Mock())
    def test_onError(self):
        data = self.plugin.onError(sentinel, sentinel)
        self.assertEquals(len(data['events']), 1)
        self.assertEquals(data['events'][0]['severity'], 4)
