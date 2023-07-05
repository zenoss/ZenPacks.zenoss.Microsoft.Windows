#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015-2018, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import Globals

from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import load_pickle_file
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import patch, Mock, sentinel
from ZenPacks.zenoss.Microsoft.Windows.utils import cluster_disk_state_string

from ZenPacks.zenoss.Microsoft.Windows.datasources.ClusterDataSource import (
    ClusterDataSourcePlugin, cluster_state_value)
from txwinrm.shell import CommandResponse

RESULTS_143596 = {
    '373a3ded-599a-482b-87af-73038d081674': 85282414592,
    'aef475c6-b4cb-4a26-aa26-66d8f7a51e5b': 342218424320,
    'ad19e6af-8064-416c-afd4-24b01488c057': 357075300352,
    'b966e176-d24e-4eb9-9461-ecfd558745f8': 242234834944,
    'fad45582-21da-4323-9f7d-6c3caa7813a3': 412222660608,
    '27f37b59-5444-4587-ba79-b6a8d7411339': 1137677946880
}

RAW_RESULTS = {
    'exit_code': 0,
    'stderr': [],
    'stdout': [
        u'res-Analysis Services (CINSTANCE01)|Online',
        u'res-Cluster Name|Online',
        u'res-IP Address 10.88.122.72|Online',
        u'res-SQL IP Address 1 (SQLNETWORK)|Online',
        u'res-SQL Network Name (SQLNETWORK)|Online',
        u'res-SQL Server (CINSTANCE01)|Online',
        u'res-SQL Server Agent (CINSTANCE01)|Online',
        u'res-SQL Server Analysis Services CEIP (CINSTANCE01)|Online',
        u'res-SQL Server CEIP (CINSTANCE01)|Online',
        u'res-Virtual Machine Cluster WMI|Failed',
        u'0f58359e-f0d9-4a96-a697-5213a4edfb9a|Online|Available Storage|win2016-kdc-01',
        u'aa35b386-5182-4cf2-a99f-670788c11347|Failed|Cluster Group|win2016-node-01',
        u'109d14aa-234b-453b-b099-1a621cc59601|Online|SQL Server (CINSTANCE01)|win2016-node-02',
        u'node-2|Up',
        u'node-1|Up',
        u'node-4|Up',
        u'be4033dc-1f74-477f-9f07-3780e1782250|Up',
        u'ac103502-487e-4406-8ec7-e1e0ac6944cd|Up',
        u'e13ed868-bdd5-4877-8a36-8769dcb290d2|Failed',
        u'6d599939-c013-4b97-9eae-f9a7f9ba8a43|Up',
        u'3982f1bc-1a87-4b9e-8e02-1f3f92ae0102|Up',
        u'c4d9126c-b657-4758-9410-c9dc84c7e15f|Up',
        u'3f430ab9-bc93-477d-9829-19c93639c89c|2|-1',
        u'860caaf4-595a-44e6-be70-285a9bb3733d|2|24254611456',
        u'9bfa9f1e-1745-4f6d-bbc5-a53048b8d380|2|9879683072']
}

RESULTS = {
    'res-Analysis Services (CINSTANCE01)': 'Online',
    'res-Cluster Name': 'Online',
    'res-IP Address 10.88.122.72': 'Online',
    'res-SQL IP Address 1 (SQLNETWORK)': 'Online',
    'res-SQL Network Name (SQLNETWORK)': 'Online',
    'res-SQL Server (CINSTANCE01)': 'Online',
    'res-SQL Server Agent (CINSTANCE01)': 'Online',
    'res-SQL Server Analysis Services CEIP (CINSTANCE01)': 'Online',
    'res-SQL Server CEIP (CINSTANCE01)': 'Online',
    'res-Virtual Machine Cluster WMI': 'Failed',
    '0f58359e-f0d9-4a96-a697-5213a4edfb9a': 'Online',
    'aa35b386-5182-4cf2-a99f-670788c11347': 'Failed',
    '109d14aa-234b-453b-b099-1a621cc59601': 'Online',
    'node-2': 'Up',
    'node-1': 'Up',
    'node-4': 'Up',
    'be4033dc-1f74-477f-9f07-3780e1782250': 'Up',
    'ac103502-487e-4406-8ec7-e1e0ac6944cd': 'Up',
    'e13ed868-bdd5-4877-8a36-8769dcb290d2': 'Failed',
    '6d599939-c013-4b97-9eae-f9a7f9ba8a43': 'Up',
    '3982f1bc-1a87-4b9e-8e02-1f3f92ae0102': 'Up',
    'c4d9126c-b657-4758-9410-c9dc84c7e15f': 'Up',
    '3f430ab9-bc93-477d-9829-19c93639c89c': '2',
    '860caaf4-595a-44e6-be70-285a9bb3733d': '2',
    '9bfa9f1e-1745-4f6d-bbc5-a53048b8d380': '2',
}


def is_empty(struct):
    if struct:
        return False
    else:
        return True


class TestClusterDataSourcePlugin(BaseTestCase):

    def setUp(self):
        self.plugin = ClusterDataSourcePlugin()

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ClusterDataSource.log', Mock())
    def test_onSuccess(self):
        config = load_pickle_file(self, 'cluster_config')
        
        for datasource in config.datasources:
            datasource.params.update({'collector_timeout':180})
        
        results = CommandResponse(
            RAW_RESULTS['stdout'],
            RAW_RESULTS['stderr'],
            RAW_RESULTS['exit_code'])
        data = self.plugin.onSuccess(results, config)
        self.assertEquals(len(data['values']), 25)
        for comp, value in RESULTS.iteritems():
            try:
                num = int(value)
                value = cluster_disk_state_string(num)
                self.assertEquals(data['values'][comp]['state'], num)
            except Exception:
                self.assertEquals(data['values'][comp]['state'][0], cluster_state_value(value), 'found {}'.format(value))
        self.assertEquals(len(data['events']), 28)
        # 24989663232 is the freespace in the pickle file
        self.assertEquals(data['values']['860caaf4-595a-44e6-be70-285a9bb3733d']['freespace'], 24254611456)

        # test for ownerchange events
        results.stdout[11] = results.stdout[11].replace('win2016-node-01', 'win2016-node-02')
        data = self.plugin.onSuccess(results, config)
        self.assertEquals(len(data['events']), 29)
        results.stdout[11] = results.stdout[11].replace('win2016-node-02', 'win2016-node-01')
        results.stdout[12] = results.stdout[12].replace('win2016-node-02', 'win2016-node-01')
        data = self.plugin.onSuccess(results, config)
        self.assertEquals(len(data['events']), 29)

    @patch('ZenPacks.zenoss.Microsoft.Windows.datasources.ClusterDataSource.log', Mock())
    def test_143596(self):
        # Cluster shared volumes are different than cluster disks
        # the status will be a string, not an int
        results = load_pickle_file(self, 'ClusterDataSourcePlugin_onSuccess_210137')[0]
        config = Mock()
        datasources = []
        for line in results.stdout:
            component = line.split('|')[0]
            datasource = Mock(
                params={
                    'eventlog': sentinel.eventlog,
                    'contexttitle': 'device',
                    'ownernode': 'IS-HVDRCL03-H04',
                    'cluster': 'IS-HVDRCL03.tcy.prv',
                    'collector_timeout': 180
                },
                datasource='DataSource',
                component=component)
            datasources.append(datasource)

        config.datasources = datasources
        config.id = 'IS-HVDRCL03.tcy.prv'
        data = self.plugin.onSuccess(results, config)
        for k, v in RESULTS_143596.iteritems():
            self.assertEquals(data['values'][k]['freespace'], v)
            self.assertEquals(data['values'][k]['state'], 2)
        csvs = set(RESULTS_143596.keys())
        evts = [evt for evt in data['events'] if evt.get('component', '') in csvs]
        for evt in evts:
            self.assertEquals(
                evt['summary'],
                'Last state of component device was Online')


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
