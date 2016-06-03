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
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import MagicMock, sentinel

from ZenPacks.zenoss.Microsoft.Windows.datasources.IISSiteDataSource import IISSiteDataSourcePlugin


class TestIISSiteDataSourcePlugin(BaseTestCase):
    def setUp(self):
        self.plugin = IISSiteDataSourcePlugin()
        super(TestIISSiteDataSourcePlugin, self).setUp()

    def test_onSuccess(self):
        data = self.plugin.onSuccess({}, MagicMock(
            id=sentinel.id,
            datasources=[MagicMock(params={'eventlog': sentinel.eventlog})],
        ))
        self.assertEquals(len(data['events']), 2)
        self.assertEquals("Monitoring ok", data['events'][1]['summary'])
        self.assertIn("is in Unknown state", data['events'][0]['summary'])

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
