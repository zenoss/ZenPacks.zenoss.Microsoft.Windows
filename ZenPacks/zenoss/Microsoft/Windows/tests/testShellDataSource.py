##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from twisted.python.failure import Failure
from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import sentinel, patch, Mock

from ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource import (
    ShellDataSourcePlugin
)


class TestShellDataSourcePlugin(BaseTestCase):
    def setUp(self):
        self.success = load_pickle(self, 'results')
        self.config = load_pickle(self, 'config')
        self.plugin = ShellDataSourcePlugin()

    def test_onSuccess(self):
        data = self.plugin.onSuccess(self.success, self.config)
        self.assertEquals(len(data['values']), 12)
        self.assertEquals(len(data['events']), 16)
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
