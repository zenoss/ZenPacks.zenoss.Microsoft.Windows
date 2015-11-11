##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject

from Products.DataCollector.plugins.DataMaps import ObjectMap
from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.WinMSSQL import WinMSSQL

RESULTS = dict(clear='Error parsing zDBInstances',
               device=ObjectMap(data=dict(sqlhostname='dbhost0')),
               instances=[ObjectMap(data=dict(
                   id='RTC$instance',
                   instancename='RTC',
                   title='RTC'))],
               jobs=[ObjectMap(data=dict(
                   cluster_node_server='//dbhost0\\RTC',
                   datecreated=' 5/26/2014 00:00:01 PM',
                   description='No description available.',
                   enabled='Yes',
                   id='aaee26a6-7970-4ffb-be57-cd49d0084c2d',
                   instancename='RTC$instance',
                   jobid='aaee26a6-7970-4ffb-be57-cd49d0084c2d',
                   title='syspolicy_purge_history',
                   username='sa'))],
               backups=[ObjectMap(data=dict(
                   devicetype='Disk',
                   id='RTC$instancertc_rtc',
                   instancename='RTC$instance',
                   physicallocation='c:\\Backup\\rtc.bak',
                   status='Existing',
                   title='rtc_rtc'))],
               databases=[ObjectMap(data=dict(
                   cluster_node_server='//dbhost0\\RTC',
                   collation='Latin1_General_BIN',
                   createdate='5/26/2014 7:47:57 PM',
                   defaultfilegroup='PRIMARY',
                   id='RTC$instance12',
                   instancename='RTC$instance',
                   isaccessible='True',
                   lastbackupdate=None,
                   lastlogbackupdate=None,
                   owner='sa',
                   primaryfilepath='C:\\rtc\\DbPath',
                   recoverymodel='Simple',
                   systemobject='False',
                   title='db0',
                   version='706'))]
               )


class TestProcesses(BaseTestCase):
    def setUp(self):
        self.plugin = WinMSSQL()
        self.device = StringAttributeObject()

    def test_process(self):
        data = self.plugin.process(self.device, RESULTS, Mock())
        self.assertEquals(len(data), 5)
        self.assertEquals(data[0].sqlhostname, 'dbhost0')

        # import pdb
        # pdb.set_trace()
        self.assertEquals(data[0].sqlhostname, 'dbhost0')

        self.assertEquals(data[1].maps[0].title, 'RTC')
        self.assertEquals(data[1].maps[0].instancename, 'RTC')

        self.assertEquals(data[2].maps[0].id, 'RTC$instancertc_rtc')
        self.assertEquals(data[2].maps[0].devicetype, 'Disk')
        self.assertEquals(data[2].maps[0].instancename, 'RTC$instance')
        self.assertEquals(data[2].maps[0].physicallocation, 'c:\\Backup\\rtc.bak')
        self.assertEquals(data[2].maps[0].status, 'Existing')
        self.assertEquals(data[2].maps[0].title, 'rtc_rtc')

        self.assertEquals(data[3].maps[0].cluster_node_server, '//dbhost0\\RTC')
        self.assertEquals(data[3].maps[0].datecreated, ' 5/26/2014 00:00:01 PM')
        self.assertEquals(data[3].maps[0].description, 'No description available.')
        self.assertEquals(data[3].maps[0].enabled, 'Yes')
        self.assertEquals(data[3].maps[0].id, 'aaee26a6-7970-4ffb-be57-cd49d0084c2d')
        self.assertEquals(data[3].maps[0].instancename, 'RTC$instance')
        self.assertEquals(data[3].maps[0].jobid, 'aaee26a6-7970-4ffb-be57-cd49d0084c2d')
        self.assertEquals(data[3].maps[0].title, 'syspolicy_purge_history')
        self.assertEquals(data[3].maps[0].username, 'sa')

        self.assertEquals(data[4].maps[0].cluster_node_server, '//dbhost0\\RTC')
        self.assertEquals(data[4].maps[0].collation, 'Latin1_General_BIN')
        self.assertEquals(data[4].maps[0].createdate, '5/26/2014 7:47:57 PM')
        self.assertEquals(data[4].maps[0].defaultfilegroup, 'PRIMARY')
        self.assertEquals(data[4].maps[0].id, 'RTC$instance12')
        self.assertEquals(data[4].maps[0].instancename, 'RTC$instance')
        self.assertEquals(data[4].maps[0].isaccessible, 'True')
        self.assertIsNone(data[4].maps[0].lastbackupdate)
        self.assertEquals(data[4].maps[0].owner, 'sa')
        self.assertEquals(data[4].maps[0].primaryfilepath, 'C:\\rtc\\DbPath')
        self.assertEquals(data[4].maps[0].recoverymodel, 'Simple')
        self.assertEquals(data[4].maps[0].systemobject, 'False')
        self.assertEquals(data[4].maps[0].title, 'db0')
        self.assertEquals(data[4].maps[0].version, '706')
