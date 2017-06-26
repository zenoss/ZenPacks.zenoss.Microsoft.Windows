#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import Globals  # noqa

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

STDOUT_LINES = [
    "Name--- [master] \tVersion--- 782 \tIsAccessible--- True \tID--- 1 \tOwner--- sa \tLastBackupDate--- 1/1/0001 12:00:00 AM \tCollation--- SQL_Latin1_General_CP1_CI_AS \tCreateDate--- 4/8/2003 9:13:36 AM \tDefaultFileGroup--- PRIMARY \tPrimaryFilePath--- C:\\Program Files\\Microsoft SQL Server\\MSSQL12.SQLSERVER2014\\MSSQL\\DATA \tLastLogBackupDate--- 1/1/0001 12:00:00 AM \tSystemObject--- True \tRecoveryModel--- Simple",
    "Name--- rtc_rtc\tDeviceType--- Disk \tPhysicalLocation--- c:\\Backup\\rtc.bak \tStatus---Existing",
    "jobname--- syspolicy_purge_history \tenabled--- True \tjobid--- 6f8d0472-e19a-4e66-9d23-dcbaa0463571 \tdescription--- No description available. \tdatecreated--- 6/2/2017 6:13:28 PM \tusername--- sa",
    "jobname--- \tenabled--- \tjobid--- \tdescription--- \tdatecreated--- \tusername--- ",
    "jobname--- job1 \tenabled--- True \tjobid--- \tdescription--- description \tdatecreated--- \tusername--- sa"
]


class TestProcesses(BaseTestCase):
    def setUp(self):
        self.plugin = WinMSSQL()
        self.device = StringAttributeObject()

    def test_process(self):
        data = self.plugin.process(self.device, RESULTS, Mock())
        self.assertEquals(len(data), 5)
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

        # if empty jobs, backups, or databases we need to send empty list of object maps
        RESULTS['jobs'] = []
        RESULTS['backups'] = []
        RESULTS['databases'] = []
        data = self.plugin.process(self.device, RESULTS, Mock())
        for x in xrange(2, 5):
            self.assertEquals(data[x].maps, [])

    def test_oms(self):
        self.plugin.log = Mock()
        db_om = self.plugin.get_db_om(StringAttributeObject(),
                                      "instance",
                                      "owner_node",
                                      "sqlserver",
                                      STDOUT_LINES[0])
        self.assertEquals(db_om.id, 'instance1')
        self.assertEquals(db_om.collation, 'SQL_Latin1_General_CP1_CI_AS')
        self.assertEquals(db_om.defaultfilegroup, 'PRIMARY')
        self.assertEquals(db_om.owner, 'sa')
        self.assertEquals(db_om.cluster_node_server, 'owner_node//sqlserver')
        self.assertEquals(db_om.createdate, '4/8/2003 9:13:36 AM')
        self.assertEquals(db_om.instancename, 'id')
        self.assertEquals(db_om.isaccessible, 'True')
        self.assertIsNone(db_om.lastbackupdate)
        self.assertIsNone(db_om.lastlogbackupdate)
        self.assertEquals(db_om.primaryfilepath, 'C:\\Program Files\\Microsoft SQL Server\\MSSQL12.SQLSERVER2014\\MSSQL\\DATA')
        self.assertEquals(db_om.recoverymodel, 'Simple')
        self.assertEquals(db_om.systemobject, 'True')
        self.assertEquals(db_om.version, '782')
        self.assertEquals(db_om.title, 'master')
        backup_om = self.plugin.get_backup_om(StringAttributeObject(),
                                              "instance",
                                              STDOUT_LINES[1])
        self.assertEquals(backup_om.instancename, 'id')
        self.assertEquals(backup_om.title, 'rtc_rtc')
        self.assertEquals(backup_om.devicetype, 'Disk')
        self.assertEquals(backup_om.physicallocation, 'c:\\Backup\\rtc.bak')
        self.assertEquals(backup_om.status, 'Existing')
        good_job_om = self.plugin.get_job_om(StringAttributeObject(),
                                             "sqlserver",
                                             StringAttributeObject(),
                                             "owner_node",
                                             STDOUT_LINES[2])
        self.assertEquals(good_job_om.title, 'syspolicy_purge_history')
        self.assertEquals(good_job_om.enabled, 'Yes')
        self.assertEquals(good_job_om.instancename, 'id')
        self.assertEquals(good_job_om.jobid, '6f8d0472-e19a-4e66-9d23-dcbaa0463571')
        self.assertEquals(good_job_om.description, 'No description available.')
        self.assertEquals(good_job_om.datecreated, '6/2/2017 6:13:28 PM')
        self.assertEquals(good_job_om.username, 'sa')
        self.assertEquals(good_job_om.cluster_node_server, 'owner_node//sqlserver')
        # check for job with blanks - ZPS-1676
        bad_job_om = self.plugin.get_job_om(StringAttributeObject(),
                                            "sqlserver",
                                            StringAttributeObject(),
                                            "owner_node",
                                            STDOUT_LINES[3])
        self.assertIsNone(bad_job_om)
        good_job_om = self.plugin.get_job_om(StringAttributeObject(),
                                             "sqlserver",
                                             StringAttributeObject(),
                                             "owner_node",
                                             STDOUT_LINES[4])
        self.assertEquals(good_job_om.jobid, 'sqljob_id_job1')


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestProcesses))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
