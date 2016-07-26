# ##############################################################################
# #
# # Copyright (C) Zenoss, Inc. 2015, all rights reserved.
# #
# # This content is made available according to terms specified in
# # License.zenoss under the directory where your Zenoss product is installed.
# #
# ##############################################################################
#

from twisted.python.failure import Failure
from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import sentinel, patch, Mock, MagicMock

from ZenPacks.zenoss.Microsoft.Windows.datasources.ServiceDataSource import ServicePlugin


class TestServiceDataSourcePlugin(BaseTestCase):
    def setUp(self):
        self.success = load_pickle(self, 'results')
        self.config = load_pickle(self, 'config')
        self.plugin = ServicePlugin()
        self.context = {'modes': ['Auto'],
                        'mode': 'Auto',
                        'monitor': True,
                        'severity': 3,
                        'manual': False,
                        'alertifnot': 'Running',
                        }

        self.ds = [MagicMock(params={'eventlog': sentinel.eventlog,
                                     'winservices': self.context,
                                     'usermonitor': False,
                                     'servicename': 'aspnet_state',
                                     'severity': 3,
                                     'alertifnot': 'Running'
                                     })]

    def test_onSuccess(self):
        data = self.plugin.onSuccess(self.success, MagicMock(
                                     id=sentinel.id,
                                     datasources=self.ds,
                                     ))
        self.assertEquals(len(data['events']), 2)
        self.assertEquals(data['events'][0]['summary'],
                          'Service Alert: aspnet_state has changed to Stopped state')
        self.assertEquals(data['events'][1]['summary'],
                          'Windows Service Check: successful service collection')

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ServiceDataSource.log', Mock())
    def test_onError(self):
        f = None
        try:
            f = Failure('foo')
        except TypeError:
            f = Failure()
        data = self.plugin.onError(f, MagicMock(
            id=sentinel.id,
            datasources=self.ds,
        ))
        self.assertEquals(len(data['events']), 1)
        self.assertEquals(data['events'][0]['severity'], 4)
