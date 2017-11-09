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

from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle_file
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import patch, Mock
from ZenPacks.zenoss.Microsoft.Windows.utils import cluster_disk_state_string
from Products.ZenModel.ZVersion import VERSION

from ZenPacks.zenoss.Microsoft.Windows.datasources.ClusterDataSource import (
    ClusterDataSourcePlugin, cluster_state_value)

RESULTS = {
    'res-Analysis Services (CINSTANCE01)': 'Online',
    'res-Cluster Disk 1': 'Online',
    'res-Cluster IP Address': 'Online',
    'res-Cluster Name': 'Online',
    'res-SQL IP Address 1 (SQLNETWORK)': 'Online',
    'res-SQL Network Name (SQLNETWORK)': 'Online',
    'res-SQL Server (CINSTANCE01)': 'Online',
    'res-SQL Server Agent (CINSTANCE01)': 'Online',
    'res-SQL Server Analysis Services CEIP (CINSTANCE01)': 'Online',
    'res-SQL Server CEIP (CINSTANCE01)': 'Online',
    'res-Virtual Machine Cluster WMI': 'Failed',
    '0f58359e-f0d9-4a96-a697-5213a4edfb9a': 'Offline',
    'aa35b386-5182-4cf2-a99f-670788c11347': 'Failed',
    '109d14aa-234b-453b-b099-1a621cc59601': 'Online',
    'node-2': 'Up',
    'node-1': 'Up',
    'node-4': 'Up',
    'be4033dc-1f74-477f-9f07-3780e1782250': 'Up',
    '2bccf6d0-c176-4020-ac9f-d8babed4b1c6': 'Up',
    'e13ed868-bdd5-4877-8a36-8769dcb290d2': 'Up',
    '3982f1bc-1a87-4b9e-8e02-1f3f92ae0102': 'Up',
    '860caaf4-595a-44e6-be70-285a9bb3733d': '2'}


def is_empty(struct):
    if struct:
        return False
    else:
        return True


class TestClusterDataSourcePlugin(BaseTestCase):

    def setUp(self):
        self.plugin = ClusterDataSourcePlugin()

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ShellDataSource.log', Mock())
    def test_onSuccess(self):
        if VERSION.startswith('4'):
            return
        datasources = load_pickle_file(self, 'cluster_datasources')
        results = load_pickle_file(self, 'ClusterDataSourcePlugin_onSuccess_161027')[0]
        config = Mock()
        config.datasources = datasources
        config.id = datasources[0].device
        data = self.plugin.onSuccess(results, config)
        self.assertEquals(len(data['values']), 22)
        for comp, value in RESULTS.iteritems():
            try:
                num = int(value)
                value = cluster_disk_state_string(num)
                self.assertEquals(data['values'][comp]['state'], num)
            except Exception:
                self.assertEquals(data['values'][comp]['state'][0], cluster_state_value(value), 'found {}'.format(value))
        self.assertEquals(len(data['events']), 26)


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestClusterDataSourcePlugin))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
