#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from select import select

import Globals  # noqa

from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock, patch
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject, load_pickle_file
from ZenPacks.zenoss.Microsoft.Windows.tests.ms_sql_always_on_test_data import defer, ALWAYS_ON_COLLECT_RESULTS, \
    DummySQLCommander, create_ao_device_proxy, DB_LOGINS, HOST_USER_NAME, HOST_USER_PASSWORD

from Products.DataCollector.plugins.DataMaps import ObjectMap
from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.WinMSSQL import WinMSSQL

try:
    import crochet
    crochet.setup()
    CROCHET_AVAILABLE = True
except ImportError:
    crochet = None
    CROCHET_AVAILABLE = False


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
    "job_jobname--- syspolicy_purge_history job_enabled--- True job_jobid--- 6f8d0472-e19a-4e66-9d23-dcbaa0463571 job_description--- No description available. job_datecreated--- 6/2/2017 6:13:28 PM job_username--- sa",
    "job_jobname--- job_enabled--- job_jobid--- job_description--- job_datecreated--- job_username--- ",
    "job_jobname--- job1 job_enabled--- True job_jobid--- job_description--- description job_datecreated--- job_username--- sa",
    "job_jobname--- job2 job_enabled--- True job_jobid--- job_description--- description ",
    "more description",
    "one more line",
    "job_datecreated--- job_username--- sa"
]

COGNIZANT_RESULTS = [
    u'job_jobname--- APP_Job_uspInsertShiftWasteEventsWeekly job_enabled--- False job_jobid--- 94c66ad2-c2fb-4425-879c-7d1f0457b11e'
    ' job_description--- Application job : Run SP uspInsertShiftWasteEventsWeekly every Wednesday 00:10 AM',
    u'job_datecreated--- 8/7/2013 12:11:46 AM job_username--- wwAdmin']

UNPACK_RESULTS = [
    u'job_jobname--- -- Dell DBA - Monitoring Mirroring job_enabled--- True job_jobid--- 86b8478f-d3f7-4857-ba5d-b071aaf5106a job_description--- No description available. job_datecreated--- 9/12/2017 3:02:11 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Archive DB Size and Space job_enabled--- False job_jobid--- d8c86d2b-b57f-49e8-90b6-0c35ade065c4 job_description--- No description available. job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Check Drive Space (@ Every 2 Hour) job_enabled--- False job_jobid--- 01e4a307-c883-49c0-bf28-cffe69124a4f job_description--- No description available. job_datecreated--- 4/25/2014 4:14:58 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Check Log Space (@ Every 19 Minutes) job_enabled--- False job_jobid--- a9f27ff9-3f53-4193-8d04-e5c15791f037 job_description--- No description available. job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - DBCC ALTERINDEX (Weekly) job_enabled--- False job_jobid--- cb42609e-dea9-4d92-b679-f910570187c2 job_description--- No description available. job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - DBCC CHECKDB (Weekly) job_enabled--- False job_jobid--- 5ebd0159-d308-4e83-bcff-3c37c4e2394c job_description--- DBCC CHECKDB run using setting in config table job_datecreated--- 4/25/2014 4:14:58 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - DBCC UPDATESTATS  (Weekly) job_enabled--- False job_jobid--- 49bd4910-7124-4910-b638-cd60adfca1de job_description--- No description available. job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - DBCC UPDATEUSAGE  (Weekly) job_enabled--- False job_jobid--- 04c2e263-e8ac-4a76-820b-164d063466f8 job_description--- No description available. job_datecreated--- 4/25/2014 4:14:58 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Diff Backup (Daily) job_enabled--- False job_jobid--- a9b066d1-7900-469a-85b3-883b94c7b2ae job_description--- Diff Backup of all databases as per configuration table (tbl_DellDBA_maintenance_config) job_datecreated--- 4/25/2014 4:14:58 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Filegroup Backup job_enabled--- False job_jobid--- ab7ce634-1bae-421f-a597-893c5247733e job_description--- No description available. job_datecreated--- 4/25/2014 4:14:58 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Full Backup (Daily) job_enabled--- False job_jobid--- 9c14893b-aa8f-4f46-a063-e24c029fa77b job_description--- Full Backup of all databases as per configuration table (tbl_DellDBA_maintenance_config) job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Generate Login Script (Daily) job_enabled--- False job_jobid--- e8e3cc1e-4946-48d5-83e2-8ad73ddf2068 job_description--- Generate login script with existing password job_datecreated--- 4/25/2014 4:14:58 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Long Running Jobs (@ Every 23 Minutes) job_enabled--- False job_jobid--- a5ec79a7-b09f-4b2d-8274-f02043a1c523 job_description--- No description available. job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - MSDB Clean Up (weekly) job_enabled--- False job_jobid--- d5a63c35-a20a-46b1-b7cd-3aa2d529a692 job_description--- No description available. job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Query Performance CPU (On Demand) job_enabled--- False job_jobid--- 5f65b4b4-ce4f-4a98-b543-d41f6b9dd5e3 job_description--- TOP CPU Intensive Queries',
    u'Would identify query and execution plan in XML Format',
    u'Query the table tbl_DellDBA_query_perf_analysis_cpu for the results job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Query Performance FRS (On Demand) job_enabled--- False job_jobid--- d5c4f6f1-f3e3-4bd4-9176-b48de24ca95d job_description--- Frequently Recompiled statements',
    u'Identify Queries in cache that have high recompile executions',
    u'Query the table tbl_DellDBA_query_perf_analysis_frs for the results job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Query Performance IO (On Demand) job_enabled--- False job_jobid--- 6aa4e53e-cb19-4e58-90b5-9e90662e475d job_description--- I/O Intensive Queries',
    u'Would identify queries with high I/O performance',
    u'Query the table tbl_DellDBA_query_perf_analysis_io for the results job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Query Performance MII (On Demand) job_enabled--- False job_jobid--- 861ed92c-fa54-455d-b173-a3ef2b0d4c06 job_description--- Missing Indexes Information',
    u'Identify queries that may (or may not) be missing indexes based on execution stats,',
    u'Query the table tbl_DellDBA_query_perf_analysis_mii for the results job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Recycle SQL error logs (@ two weeks) job_enabled--- False job_jobid--- 658f2794-f450-461b-9f18-4c62e0c76eb4 job_description--- This script is meant to recycle the SQL error logs every two weeks in order to have a small size of the error log file. job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Runbook (Daily) job_enabled--- False job_jobid--- d0ab2064-1b52-411e-ba8d-aba5879e76b0 job_description--- Gets the Runbook of the current instance and exports the information to a file job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u"job_jobname--- -- DellDBA - Start Trace (On Demand) job_enabled--- False job_jobid--- 8397a352-8536-4c03-9b85-4750c77cdd97 job_description--- Pass parameters as shown here -  DellDBA..usp_DellDBA_StartTrace '<databasename>', '<file path/directory>' , <maxfilesize> job_datecreated--- 4/25/2014 4:14:58 PM job_username--- sa",
    u'job_jobname--- -- DellDBA - Stop Trace (On Demand) job_enabled--- False job_jobid--- 0c62d89c-3ecf-4542-b755-9d48876e03aa job_description--- No description available. job_datecreated--- 4/25/2014 4:14:58 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - TempDB Monitoring Objects (On Demand) job_enabled--- False job_jobid--- 7bdfca8d-68a2-448c-9aed-22f99a324b87 job_description--- No description available. job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - TempDB Monitoring Space Usage (On Demand) job_enabled--- False job_jobid--- b2bb3f3e-198d-4778-a8e2-3963767532a0 job_description--- No description available. job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - TempDB Monitoring Version Store (On Demand) job_enabled--- False job_jobid--- 0a1ff53b-8cb7-45b5-9e95-f13e9362f706 job_description--- No description available. job_datecreated--- 4/25/2014 4:14:59 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Track Blocking SPID (On Demand) job_enabled--- False job_jobid--- d6dcedb5-abed-48dc-8d7b-7342177f7b17 job_description--- This is recommeded to be continuous on Server where blocking is reported very high. Hence Schedule for this should be continuous. job_datecreated--- 4/25/2014 4:14:58 PM job_username--- sa',
    u'job_jobname--- -- DellDBA - Trans. Log Backup job_enabled--- False job_jobid--- 3950fd7b-9c8a-41fe-b1a0-6f6aaf31d008 job_description--- No description available. job_datecreated--- 4/25/2014 4:14:58 PM job_username--- sa',
    u'job_jobname--- --- Maint Hourly shrink all log files job_enabled--- False job_jobid--- 6d1b2cc6-1428-474f-8002-f78bb136c8d9 job_description--- No description available. job_datecreated--- 11/9/2015 2:37:46 PM job_username--- sa',
    u'job_jobname--- --- MAINT Rebuild Store Indexes with page compression job_enabled--- False job_jobid--- d1d7f3c9-6131-42e6-92d8-18a819a737a3 job_description--- No description available. job_datecreated--- 7/8/2015 1:14:18 PM job_username---',
    u'job_jobname--- --- SYNC BIProd Copy BTSDD From RatProd job_enabled--- False job_jobid--- 336f939b-a465-4efc-94e5-00bed0e8c28e job_description--- No description available. job_datecreated--- 11/19/2014 9:18:24 AM job_username---',
    u'job_jobname--- --- SYNC BIProd Copy ENHDD From RatProd job_enabled--- False job_jobid--- a60a1e60-440c-45eb-a4ad-c27deac281bf job_description--- No description available. job_datecreated--- 12/8/2014 9:43:52 AM job_username---',
    u'job_jobname--- --- SYNC BIProd Refresh PacePos from RATPROD job_enabled--- False job_jobid--- 72febc4b-4167-4acc-b639-c46fa177f44c job_description--- No description available. job_datecreated--- 11/19/2014 1:26:18 PM job_username---',
    u'job_jobname--- --- SYNC BIProd Refresh Reservations from RATPROD job_enabled--- False job_jobid--- 63c53027-6358-4291-b9a7-cbd6520f9f43 job_description--- No description available. job_datecreated--- 11/19/2014 1:24:35 PM job_username---',
    u'job_jobname--- ~Quartly BI FIle job_enabled--- False job_jobid--- 824cb320-8a44-416b-896f-4749b9963c6c job_description--- No description available. job_datecreated--- 1/16/2015 4:58:52 PM job_username---',
    u'job_jobname--- Adhoc Rebuild BTS tables job_enabled--- False job_jobid--- 3d166c85-c669-4f2f-bdbd-6c1fdaa8b059 job_description--- No description available. job_datecreated--- 8/31/2015 11:09:29 AM job_username--- HQ\\stevenrjohnson',
    u'job_jobname--- Adhoc Special BTS Sync March 27 job_enabled--- False job_jobid--- 806991ca-feea-4340-8f0d-9855bdc5896b job_description--- No description available. job_datecreated--- 3/27/2016 5:59:53 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Adhoc SYNC EDD job_enabled--- False job_jobid--- f6f70227-d334-4eb9-801e-00e1168c25fd job_description--- No description available. job_datecreated--- 3/27/2016 3:35:15 PM job_username--- sa',
    u'job_jobname--- Adhoc_CFC_Test job_enabled--- False job_jobid--- 333f7faa-e6a7-4063-9747-afa933512369 job_description--- No description available. job_datecreated--- 1/5/2017 2:03:48 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Adhoc_Daily_PropInfo_Dev_Delta job_enabled--- False job_jobid--- 96029ac9-c083-4db4-a8ad-26eb5e9badc7 job_description--- No description available. job_datecreated--- 9/27/2016 9:46:12 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Adhoc_Daily_PropInfo_Dev_Test job_enabled--- False job_jobid--- c64d34c8-202e-4899-8e2e-710053f46064 job_description--- No description available. job_datecreated--- 9/20/2016 2:30:12 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Adhoc_Daily_PropInfo_Refresh_RATDEV_key_tables job_enabled--- False job_jobid--- 916028e1-077e-4dcc-a104-2ae089e6d3b1 job_description--- No description available. job_datecreated--- 9/29/2016 10:24:38 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Adhoc_FMS_WorkSlate_Special job_enabled--- False job_jobid--- 608adda3-693f-4556-a93c-f7a3da1c8094 job_description--- No description available. job_datecreated--- 8/17/2016 8:33:47 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Adhoc_MktShare_Rebase job_enabled--- False job_jobid--- 1bd7cc00-0d7f-4b97-a976-eae77ed0aecb job_description--- No description available. job_datecreated--- 2/15/2017 2:16:53 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Adhoc_Peak_QA_for_Irina job_enabled--- False job_jobid--- 973b0850-760e-4d2b-a6ac-f33167e64e79 job_description--- No description available. job_datecreated--- 9/8/2016 9:48:53 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- AdHoc_SecondayMCatAssignment job_enabled--- False job_jobid--- 455fe45b-f0ff-432a-be2e-721f706414f6 job_description--- No description available. job_datecreated--- 10/3/2014 10:53:26 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Agent history clean up: distribution job_enabled--- False job_jobid--- 1b9270ff-d194-4816-9257-cf6ba315029f job_description--- Removes replication agent history from the distribution database. job_datecreated--- 11/16/2016 4:23:49 PM job_username---',
    u'job_jobname--- Daily DMPEAudits job_enabled--- False job_jobid--- 4744ed80-7f97-40d5-8be3-c1d985ff9b41 job_description--- No description available. job_datecreated--- 6/20/2014 5:54:37 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily Reset Freshness Flags job_enabled--- False job_jobid--- ff51c5fb-7800-4707-b932-0b493e7e54cc job_description--- No description available. job_datecreated--- 3/9/2015 3:01:04 PM job_username--- HQ\\stevenrjohnson',
    u'job_jobname--- Daily_Backup_Object_Definitions job_enabled--- False job_jobid--- a4267e04-d372-4497-8d76-1f7d6d6a3217 job_description--- No description available. job_datecreated--- 3/3/2017 11:54:42 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Daily_BTSAccounts_from_BI job_enabled--- False job_jobid--- 33c9206f-0da8-4f76-bbf0-f8b0b2960e1f job_description--- No description available. job_datecreated--- 10/19/2015 3:09:28 PM job_username---',
    u'job_jobname--- Daily_FailedJobReport job_enabled--- False job_jobid--- 6df4c345-9fc6-47b1-bae2-da482a8fa490 job_description--- No description available. job_datecreated--- 4/5/2013 1:42:48 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_fmsImport job_enabled--- False job_jobid--- fc7e84a4-cf42-4517-bd18-9895bd96a345 job_description--- Execute package: Weekly fmsDetail job_datecreated--- 1/6/2015 3:57:34 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_GI_UpdateBrcSrc job_enabled--- False job_jobid--- 6b8b1dd5-f6c5-4f39-963a-55490bc7975a job_description--- No description available. job_datecreated--- 12/13/2016 12:49:16 PM job_username---',
    u'job_jobname--- Daily_MappingTablesExport job_enabled--- False job_jobid--- 7e1a2dd3-21b3-49c5-ab5b-1374a80433c1 job_description--- No description available. job_datecreated--- 8/15/2013 8:10:44 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_Market Vision Rate Shop job_enabled--- False job_jobid--- 7ace8e22-b65a-4463-a791-2ce930c6409a job_description--- No description available. job_datecreated--- 6/27/2016 5:29:56 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_ONQSM_Extract job_enabled--- False job_jobid--- 84a0beed-8967-42aa-8403-9f203835b3e9 job_description--- No description available. job_datecreated--- 10/22/2013 3:37:30 PM job_username--- sa',
    u'job_jobname--- Daily_Property Master Extracts job_enabled--- False job_jobid--- ce769dfa-9a3e-4cc5-a0d6-a6425811e111 job_description--- No description available. job_datecreated--- 9/18/2014 5:00:19 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_PropInfo job_enabled--- False job_jobid--- 93d82496-6dec-4988-b928-ce83f1353eff job_description--- No description available. job_datecreated--- 11/21/2014 3:38:14 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_RMCCAdminCheck job_enabled--- False job_jobid--- 601adbac-f8a4-47f9-96bc-970dc5fad55f job_description--- Execute package: RMCC Admin Check job_datecreated--- 2/11/2015 2:20:27 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_SRP_ProgramTablesToMapSRP job_enabled--- False job_jobid--- ec9b2261-a066-46e3-a9ee-490771f0b031 job_description--- This job will insert into map.SRP new SRPs created in ProgramTables and update map.SRP changed SRPs in ProgramTables daily job_datecreated--- 8/28/2015 1:32:54 PM job_username--- sa',
    u'job_jobname--- Daily_SRPQC_Data_Transfer job_enabled--- False job_jobid--- 25432c45-c8d8-47db-8789-9e9171ac0fae job_description--- No description available. job_datecreated--- 4/27/2016 3:28:19 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Daily_SRPSetup job_enabled--- False job_jobid--- 5831ad24-f132-4548-92bd-472fa1ea1f00 job_description--- No description available. job_datecreated--- 8/8/2016 5:16:00 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_SRPSetup_BTA_RoomType job_enabled--- False job_jobid--- c9b1998b-ad2d-454c-8bff-73b6bd560d81 job_description--- No description available. job_datecreated--- 4/20/2016 10:22:00 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Daily_SRPSetup_ManualClearStatus job_enabled--- False job_jobid--- 3a1317ab-e4eb-4c46-ba17-8eea08e2600f job_description--- No description available. job_datecreated--- 10/10/2014 3:56:55 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Daily_SRPSetup_ManualClearWExceptions job_enabled--- False job_jobid--- 56ce92f1-d060-4052-bad6-80e440d35f15 job_description--- No description available. job_datecreated--- 5/13/2015 11:50:01 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Daily_SRPSetup_ManualSetRATPRODUnderInvestigation job_enabled--- False job_jobid--- 5b470a23-0269-4b9f-8048-6ac311fadce2 job_description--- No description available. job_datecreated--- 1/28/2015 8:10:26 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Daily_SRPSetup_ManualSetReadyToSync job_enabled--- False job_jobid--- 4426e28d-9149-48e3-86df-ac6c77ebed0a job_description--- No description available. job_datecreated--- 12/24/2014 8:04:05 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Daily_SRPSetup_NOSYNC job_enabled--- False job_jobid--- 12d686b1-e706-4e9a-9baf-4859b70f1442 job_description--- No description available. job_datecreated--- 10/21/2016 1:37:03 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_SRPSetup_QA job_enabled--- False job_jobid--- 2111ca07-72e3-4b99-a4b0-609355a6e9e0 job_description--- No description available. job_datecreated--- 10/19/2016 8:45:49 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_SRPSetup_Test job_enabled--- False job_jobid--- 5a5d0178-3053-4427-9806-089eaf6c7885 job_description--- No description available. job_datecreated--- 6/20/2014 1:57:41 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_TempDBMaintenance job_enabled--- False job_jobid--- cdeefc32-44c8-4100-bc2a-0e56b076218f job_description--- No description available. job_datecreated--- 4/16/2013 3:58:33 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Daily_TravelClick_PropertyInfo_Transfer job_enabled--- False job_jobid--- 986bf8b1-fd07-4eed-8e87-13826289cbd3 job_description--- No description available. job_datecreated--- 8/4/2016 1:30:05 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Daily_XchangeRates job_enabled--- False job_jobid--- 6d740f16-4984-40af-ab7e-06ef93e78ed3 job_description--- No description available. job_datecreated--- 1/15/2013 5:37:39 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Database Mirroring Monitor Job job_enabled--- True job_jobid--- 97c15ac6-55ae-4983-b7a8-ec4ef23fc99d job_description---  job_datecreated--- 7/28/2017 3:46:00 PM job_username--- HQ\\htribouillier',
    u'job_jobname--- DBA - Trigger Status Monitor job_enabled--- False job_jobid--- 0590b44d-232e-4763-828e-9d498d6329b2 job_description--- No description available. job_datecreated--- 4/25/2014 11:16:00 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- Distribution clean up: distribution job_enabled--- False job_jobid--- c02226f4-54a7-4064-8991-cd91b17f1aba job_description--- Removes replicated transactions from the distribution database. job_datecreated--- 11/16/2016 4:23:49 PM job_username---',
    u'job_jobname--- HalfHourly_DriveSpaceCheck job_enabled--- False job_jobid--- a19c7cf5-97ce-4563-8ae3-1b81d553cef2 job_description--- No description available. job_datecreated--- 8/20/2013 1:58:39 PM job_username--- sa',
    u'job_jobname--- Hourly_AutomatedEmail job_enabled--- False job_jobid--- 9fb757f4-fbed-4020-b197-49517214d351 job_description--- Execute package: Hourly AutomatedEmail job_datecreated--- 2/3/2015 1:53:01 PM job_username--- sa',
    u'job_jobname--- Hourly_EIS_BRAT_Revenue_Stats_To_FMORIN job_enabled--- False job_jobid--- d2852d8e-c890-4004-91fd-9c063925a665 job_description--- No description available. job_datecreated--- 4/14/2016 1:26:27 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Hourly_Empty_ Mapping_ Tables_ Alert job_enabled--- False job_jobid--- e041e0a2-b1cd-41de-832d-15998cade023 job_description--- No description available. job_datecreated--- 8/12/2013 6:15:47 PM job_username--- HQ\\stevenrjohnson',
    u'job_jobname--- Hourly_LongRunningJobs job_enabled--- False job_jobid--- a0cbbecb-f6e3-4d58-9e49-13fc161500ea job_description--- No description available. job_datecreated--- 8/15/2013 11:49:53 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- Hourly_TableStatus job_enabled--- False job_jobid--- 5ed2f821-1e3b-48dd-846e-a8cdc72473e6 job_description--- No description available. job_datecreated--- 6/28/2013 5:18:16 PM job_username--- sa',
    u'job_jobname--- Monthly OnQ Insider MktShare Extract job_enabled--- False job_jobid--- f5c452db-6a3b-4125-9381-97be5be4eb4c job_description--- No description available. job_datecreated--- 10/12/2015 2:56:06 PM job_username--- HQ\\stevenrjohnson',
    u'job_jobname--- Monthly_Fin_Franchise job_enabled--- False job_jobid--- d986387d-415a-44be-9471-adebd7d82a31 job_description--- No description available. job_datecreated--- 2/21/2017 3:50:40 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_HLBFS_DEANQ_Clear job_enabled--- False job_jobid--- 782d2934-c957-4f08-8aed-cb408f7effe5 job_description--- No description available. job_datecreated--- 10/5/2016 3:10:04 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_HLBFS_New_Manual_Set_Cleared job_enabled--- False job_jobid--- 3eaba1f7-697a-44d9-b22e-7daddea4190f job_description--- No description available. job_datecreated--- 3/14/2016 5:45:08 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_IATACognos job_enabled--- False job_jobid--- d9f0a0c7-3d2c-45b0-b9b8-579844ec0f60 job_description--- Import file from Frederic job_datecreated--- 11/23/2015 9:51:41 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_Medallia_CompSet_Export job_enabled--- False job_jobid--- 2bd1b705-59b2-43a2-9623-59848efb606f job_description--- No description available. job_datecreated--- 2/28/2017 3:25:04 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_Mktshare_CodeDef_Census_Pipeline job_enabled--- False job_jobid--- ea91a6c5-1a43-4265-8f77-ab4f211b371b job_description--- No description available. job_datecreated--- 7/26/2016 5:24:48 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Monthly_Mktshare_Final job_enabled--- False job_jobid--- c6b56941-c023-4bc0-ba65-168c27b55afd job_description--- No description available. job_datecreated--- 7/26/2016 6:28:46 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Monthly_Mktshare_Final_SYNC job_enabled--- False job_jobid--- 164b0621-5cbf-4ad4-8a26-521f22d41b56 job_description--- No description available. job_datecreated--- 7/26/2016 6:37:48 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_Mktshare_Legacy job_enabled--- False job_jobid--- bb495fef-325c-4dd7-83f8-ee6960d83b69 job_description--- No description available. job_datecreated--- 2/6/2014 12:34:39 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Monthly_Nor1_Property_Extract job_enabled--- False job_jobid--- edb1d09e-ba0f-4b78-b0de-0114648c3347 job_description--- No description available. job_datecreated--- 4/26/2016 3:52:00 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANHLT_Raw_To_Validation job_enabled--- False job_jobid--- 4eac6354-6ffe-463b-860d-cf53cb5cc54e job_description--- No description available. job_datecreated--- 2/6/2017 10:57:18 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_Archivie_Rolling job_enabled--- False job_jobid--- 2e97bf6b-1ef2-473f-9952-e34470986c15 job_description--- No description available. job_datecreated--- 2/17/2017 2:07:58 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_CFC_Report job_enabled--- False job_jobid--- 6fa284ed-cd5c-4766-acdf-93322950d05c job_description--- No description available. job_datecreated--- 12/12/2016 1:16:08 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_CFC_Report_Actuals job_enabled--- False job_jobid--- 9c2fcabb-5f2a-4c0b-a5f1-b9d37aab997b job_description--- No description available. job_datecreated--- 12/20/2016 4:06:08 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_Clear job_enabled--- False job_jobid--- 5cc7f18f-dcf0-49ff-855f-b9bbaaf20288 job_description--- No description available. job_datecreated--- 7/13/2016 1:50:53 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_Emergency_SYNC_Detail_Summary job_enabled--- False job_jobid--- d3a48a65-8913-4265-ac64-c617e8a2273b job_description--- No description available. job_datecreated--- 2/17/2017 2:05:58 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_Mapping_Table_Sync job_enabled--- False job_jobid--- c1bb8852-1eb8-450f-b98d-164c034f5224 job_description--- No description available. job_datecreated--- 12/27/2016 5:33:38 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_MetaData job_enabled--- False job_jobid--- 6326c9fc-cd18-41de-aa49-4bfa1f8943f8 job_description--- No description available. job_datecreated--- 7/13/2016 1:02:11 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_PeakData job_enabled--- False job_jobid--- 06e3e091-9527-449b-b6bc-46226e544a84 job_description--- No description available. job_datecreated--- 3/13/2017 12:57:19 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_Remap_FaciltyIDs job_enabled--- False job_jobid--- 70df6013-1c74-41a9-a435-26c2447711db job_description--- No description available. job_datecreated--- 7/13/2016 2:12:15 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_SFTP_thru_Validation job_enabled--- False job_jobid--- cff33365-93c9-4725-8538-92e9495356aa job_description--- No description available. job_datecreated--- 7/13/2016 1:36:25 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PLANIT_Sync job_enabled--- False job_jobid--- 34e13c99-efff-4f28-8694-1259ccd8e2c1 job_description--- No description available. job_datecreated--- 7/13/2016 1:54:50 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_PropsExtract_SalesTechNonComparable job_enabled--- False job_jobid--- acd2d254-2530-404b-9b14-cf6c2b90e223 job_description--- No description available. job_datecreated--- 4/21/2016 11:07:44 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_RDRM_Extract job_enabled--- False job_jobid--- fc5216f7-db51-426e-a150-fd71433b8fbb job_description--- No description available. job_datecreated--- 6/14/2016 2:36:14 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_RiskMgmtDataFeed job_enabled--- False job_jobid--- 23e61cd9-8436-4c3b-8db4-9a5a116b85dc job_description--- No description available. job_datecreated--- 7/29/2016 11:23:49 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_SalesTech_AllPropsExport job_enabled--- False job_jobid--- 4cd4d5f1-2fe9-466b-a3cc-d8e0d9839b6f job_description--- No description available. job_datecreated--- 8/15/2016 7:09:39 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_STR_Export job_enabled--- False job_jobid--- c57df187-85e9-47d8-b43d-45e81f3ab55c job_description--- No description available. job_datecreated--- 12/29/2015 9:09:48 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Monthly_YearlyTargets job_enabled--- False job_jobid--- 8effd0dc-5ff7-4d28-a308-713bb5c80469 job_description--- Execute package: Monthly YearlyTargets job_datecreated--- 9/29/2015 1:22:48 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Quaterly reassign of Distpref job_enabled--- False job_jobid--- 6f433e7c-5914-4c93-b331-ad1e11f966ef job_description--- No description available. job_datecreated--- 3/4/2014 9:00:06 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Quaterly_RSRV Enh DailyDetails Build job_enabled--- False job_jobid--- ae0236ed-f4bd-49f8-8ec2-45316e66ca28 job_description--- No description available. job_datecreated--- 1/6/2014 9:59:05 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Reinitialize subscriptions having data validation failures job_enabled--- False job_jobid--- e43d483f-de27-4b67-852d-abc8a344efc2 job_description--- Reinitializes all subscriptions that have data validation failures. job_datecreated--- 11/16/2016 4:23:45 PM job_username---',
    u'job_jobname--- Replication agents checkup job_enabled--- False job_jobid--- 0164d142-7917-4fa4-aab2-a9833de21778 job_description--- Detects replication agents that are not logging history actively. job_datecreated--- 11/16/2016 4:23:45 PM job_username---',
    u'job_jobname--- Replication monitoring refresher for distribution. job_enabled--- False job_jobid--- ded5f1fc-3e8d-451f-b969-75884a9ecc75 job_description--- Replication monitoring refresher for distribution. job_datecreated--- 11/16/2016 4:23:49 PM job_username---',
    u'job_jobname--- RWDBRAT01PH-Base-1 job_enabled--- False job_jobid--- f39fd145-9dd6-4820-88a2-e0c067ac9a90 job_description--- No description available. job_datecreated--- 11/17/2016 2:09:10 PM job_username---',
    u'job_jobname--- RWDBRAT01PH-Base-Base_Snapshots-2 job_enabled--- False job_jobid--- c50fbb84-a745-447c-bf3c-38b70339bd3b job_description--- No description available. job_datecreated--- 11/17/2016 2:11:42 PM job_username---',
    u'job_jobname--- RWDBRAT01PH-Base-Base_Snapshots-RWDBRAT02PH-4 job_enabled--- False job_jobid--- d63bedff-a7b3-4cd4-a8c0-611ff67b7da4 job_description--- No description available. job_datecreated--- 11/17/2016 4:01:49 PM job_username---',
    u'job_jobname--- RWDBRAT01PH-Base-Base_Transactions-1 job_enabled--- False job_jobid--- 62c9433d-8ee1-45ab-9493-3d1b489df193 job_description--- No description available. job_datecreated--- 11/17/2016 2:09:13 PM job_username---',
    u'job_jobname--- RWDBRAT01PH-Base-Base_Transactions-RWDBRAT02PH-5 job_enabled--- False job_jobid--- 575bcb93-5221-4ec0-a429-7e3e86fdfdf8 job_description--- No description available. job_datecreated--- 11/17/2016 4:03:14 PM job_username---',
    u'job_jobname--- syspolicy_purge_history job_enabled--- False job_jobid--- 13b700fd-73b9-46c5-8864-4d5bfd97aea5 job_description--- No description available. job_datecreated--- 8/9/2012 8:36:56 PM job_username--- sa',
    u'job_jobname--- sysutility_get_cache_tables_data_into_aggregate_tables_daily job_enabled--- False job_jobid--- 5417287f-5280-477c-9053-4277098a2133 job_description--- At every 12:01 AM stroke, the data of the cache tables get aggregated and put into corresponding aggregate by day tables. job_datecreated--- 6/6/2014 9:39:47 AM job_username---',
    u"job_jobname--- sysutility_get_cache_tables_data_into_aggregate_tables_hourly job_enabled--- False job_jobid--- 86848f1c-786e-49d3-aa70-d33c51fc73f6 job_description--- At every hour's stroke, the data of the cache tables get aggregated and put into corresponding aggregate by hour tables. job_datecreated--- 6/6/2014 9:39:47 AM job_username--- sa",
    u'job_jobname--- sysutility_get_views_data_into_cache_tables job_enabled--- False job_jobid--- 7e91a03c-e961-4cf6-b0fd-aea9d53fda66 job_description--- Gets all the views data into corresponding cache tables after every 15 minutes job_datecreated--- 6/6/2014 9:39:47 AM job_username--- sa',
    u'job_jobname--- Weekly Epsilon Data Extract and SFTP job_enabled--- False job_jobid--- 1fd8cf8a-700a-4dba-8bda-953000d08d1c job_description--- No description available. job_datecreated--- 3/2/2015 1:13:09 PM job_username--- HQ\\stevenrjohnson',
    u'job_jobname--- Weekly_ Table growth job_enabled--- False job_jobid--- df6746e8-1202-448d-bfaf-16a0403df942 job_description--- No description available. job_datecreated--- 3/27/2015 5:04:53 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_AppleReit job_enabled--- False job_jobid--- 04fc7f6c-512d-4820-9b45-35e39cc5befe job_description--- No description available. job_datecreated--- 4/15/2016 2:31:15 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Weekly_BCP_ENHDD job_enabled--- False job_jobid--- 8f45e4e6-7f27-449d-8f7e-fa4d0fd1b228 job_description--- No description available. job_datecreated--- 1/29/2014 1:23:08 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_BI_Reservation_Counts job_enabled--- False job_jobid--- 8c2b2bf3-5bde-4133-ab2f-8e0965dfbb8f job_description--- No description available. job_datecreated--- 8/6/2015 2:03:00 PM job_username---',
    u'job_jobname--- Weekly_BIimport job_enabled--- False job_jobid--- df3ec111-c9b2-48b2-9df2-bed8011e3dd5 job_description--- No description available. job_datecreated--- 6/29/2015 10:34:57 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_BTSDailyDetails job_enabled--- False job_jobid--- 681af5b7-0d00-4d15-9a61-e8dafbca6189 job_description--- No description available. job_datecreated--- 7/8/2015 5:14:55 PM job_username---',
    u'job_jobname--- Weekly_DMPE_Server_Export_SalesTech job_enabled--- False job_jobid--- bb189eb6-0634-4ffb-b7c2-3b31cc5cadaa job_description--- No description available. job_datecreated--- 8/10/2016 4:52:41 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Weekly_EdgeExport job_enabled--- False job_jobid--- e5e20a5f-0424-4c9e-b673-35a925a81401 job_description--- No description available. job_datecreated--- 11/29/2013 1:18:35 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_Enhdailydetails job_enabled--- False job_jobid--- 1285d431-51c6-48c7-8204-21710a0d9aa2 job_description--- No description available. job_datecreated--- 11/28/2013 5:53:03 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_Franchise_Owner_Management_Export job_enabled--- False job_jobid--- fd02e7df-6cce-4f40-9725-aca4cfee9921 job_description--- No description available. job_datecreated--- 12/28/2016 10:57:27 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Weekly_HHD_ Data_Pull job_enabled--- False job_jobid--- 33c8cee7-0c9c-483c-8a93-7c98c76bd97e job_description--- No description available. job_datecreated--- 8/12/2016 1:33:57 PM job_username---',
    u'job_jobname--- Weekly_MktshareAll job_enabled--- False job_jobid--- 335372f0-64fa-4d5d-a96e-045f062c3673 job_description--- No description available. job_datecreated--- 11/28/2013 5:50:45 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_MktshareAll_with_NoSync job_enabled--- False job_jobid--- 6d3d40c5-0938-4e66-bf96-2e22dd1bd08d job_description--- No description available. job_datecreated--- 10/13/2016 12:02:08 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_OnQRM_EmailList job_enabled--- False job_jobid--- f9d38158-96da-4cdf-8110-575dfe079cb9 job_description--- No description available. job_datecreated--- 6/13/2016 9:23:26 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- Weekly_Pulse_Report_Extract job_enabled--- False job_jobid--- bb2284f5-4c81-4bf9-8fbe-8b74280941dc job_description--- Weekly Pulse Report Extract job_datecreated--- 9/8/2014 3:40:38 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_RMS RTLVLCTA job_enabled--- False job_jobid--- 12505262-cecd-44c2-bd09-252b9d721192 job_description--- No description available. job_datecreated--- 2/15/2013 1:09:26 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_RMSOverBooking job_enabled--- False job_jobid--- 3d7217b5-0b9a-4fce-8d2c-cac19b5948e1 job_description--- No description available. job_datecreated--- 2/15/2013 1:12:29 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_RMSPaceandPosition job_enabled--- False job_jobid--- 5fec85a8-306a-4c0f-950e-3f5b0c6fe2b5 job_description--- No description available. job_datecreated--- 10/28/2013 1:05:10 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_Tableau_Data_Pulls job_enabled--- False job_jobid--- a1b33ce3-4205-49db-9338-af81772d4e86 job_description--- No description available. job_datecreated--- 8/12/2016 9:32:01 AM job_username---',
    u'job_jobname--- Weekly_Update_Statistics job_enabled--- False job_jobid--- f3d7c476-be23-45a4-8d6c-d5315d3fe1fc job_description--- updates stistics and index usage stats for the query optimizer. job_datecreated--- 7/25/2013 12:09:07 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Weekly_WhiteLodging job_enabled--- False job_jobid--- 5b8a1987-0d43-4cb0-bdb2-994a55c133c7 job_description--- No description available. job_datecreated--- 12/22/2015 4:41:58 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Yearly_BTSclientRefresh job_enabled--- False job_jobid--- 15c4ce93-2218-44e1-8dd1-a268aa3b8826 job_description--- No description available. job_datecreated--- 2/21/2014 10:53:26 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- Yearly_Enhdailydetails job_enabled--- False job_jobid--- 9d0e0ee9-f7a5-4570-8668-912b8586ea0c job_description--- No description available. job_datecreated--- 3/19/2014 1:46:41 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Yearly_InternationalRPITargets job_enabled--- False job_jobid--- 9d5ca8ba-f2ec-4806-b700-8e0399fcd6f1 job_description--- No description available. job_datecreated--- 12/4/2015 4:21:48 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- Yearly_PacePositionYearlyExchangeRate job_enabled--- False job_jobid--- 555b751d-3f73-4680-99d9-6f9cf8e8f06d job_description--- No description available. job_datecreated--- 3/19/2014 1:47:23 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Yearly_ReassignDistprefid job_enabled--- False job_jobid--- 0edc9989-0113-468a-ad72-df32161bff4f job_description--- No description available. job_datecreated--- 12/31/2013 8:04:35 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- Yearly_ReservationExchangeRate job_enabled--- False job_jobid--- 1952b353-50b0-4b20-8c0b-b340324aefa4 job_description--- No description available. job_datecreated--- 3/19/2014 1:47:57 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- zzz--- SYNC BIProd Copy ActDetail (Monthly) to RatProd job_enabled--- False job_jobid--- 2b19119f-7419-4980-a37f-6e6ec71c4718 job_description--- No description available. job_datecreated--- 11/21/2014 12:27:13 PM job_username---',
    u'job_jobname--- zzzDaily Run MB Data Import from HFWDBETL01PH (RatDB)_delete job_enabled--- False job_jobid--- 112ba9cc-2381-4249-89ef-983681db545a job_description--- No description available. job_datecreated--- 4/8/2014 2:55:45 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- zzzDaily_BusinessUnit_Mapping moved to analytics job_enabled--- False job_jobid--- 04175398-d32d-4bbb-b262-69d4b10fcae1 job_description--- No description available. job_datecreated--- 11/11/2016 3:46:24 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- zzzDaily_fmsForecast job_enabled--- False job_jobid--- d972e88b-cb68-4626-9235-a6ff67c27c7e job_description--- Execute package: daily fmsForecast job_datecreated--- 2/22/2016 1:39:44 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- zzzDaily_fmsSummary job_enabled--- False job_jobid--- 757e24a1-78c5-479c-a6b4-39c44a3566c0 job_description--- Execute package: daily fmsSummary job_datecreated--- 9/5/2014 10:36:26 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- zzzDaily_Peak_EDW_DMPE_PacePos MOVED TO BIPROD job_enabled--- False job_jobid--- 321e6c8f-fa93-40ce-ad88-f522a4a2a197 job_description--- No description available. job_datecreated--- 4/12/2016 10:57:18 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- zzzDaily_SRPRMSRatesBI_Delete201702 job_enabled--- False job_jobid--- a8c42ca2-6343-4b53-8009-67e9f97d2628 job_description--- No description available. job_datecreated--- 3/6/2014 11:57:11 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- zzzHelpTrakLoadAllConsmoved to analytics job_enabled--- False job_jobid--- 56f6c727-f73f-4aa0-bb83-b84ff9231e15 job_description--- No description available. job_datecreated--- 11/18/2016 2:26:12 PM job_username---',
    u'job_jobname--- zzzHourly UAP Band Aid fix_delete20160501 job_enabled--- False job_jobid--- c8c94abc-0280-4799-8be2-0db9a7eb4274 job_description--- No description available. job_datecreated--- 12/17/2015 11:23:59 AM job_username--- HQ\\svcRAT',
    u'job_jobname--- zzzLiteSpeed Backup Fast Compression RWDBRAT01PH.SRPSetup job_enabled--- False job_jobid--- 7d0a7cd4-54b7-43c9-8031-ae79826fc034 job_description--- LiteSpeed backup of SRPSetup job_datecreated--- 10/7/2015 5:03:57 PM job_username---',
    u'job_jobname--- zzzLiteSpeed Backup Fast Compression RWDBRAT01PH.Store job_enabled--- False job_jobid--- 266c9f0c-4996-45b0-adec-d4289bbf65ed job_description--- LiteSpeed backup of Store job_datecreated--- 10/29/2015 3:22:50 PM job_username---',
    u'job_jobname--- zzzLiteSpeed Backup Fast Compression RWDBRAT01PH.Store 1 job_enabled--- False job_jobid--- 225911f1-d558-4ee9-b97a-fefc1fbcfb7c job_description--- LiteSpeed backup of Store job_datecreated--- 11/3/2015 4:24:09 PM job_username---',
    u'job_jobname--- zzzLiteSpeed\u2122 for SQL Server Update Native Backup statistics job_enabled--- False job_jobid--- 1ba082a3-fed0-43ad-b003-a08815839baa job_description--- LiteSpeed for SQL Server Update Native Backup statistics job_datecreated--- 9/30/2015 2:21:16 PM job_username--- HQ\\stevenrjohnson',
    u'job_jobname--- zzzMonthly_HLBFS_New_Manual_Set_Ready_To_SYNC job_enabled--- False job_jobid--- a706f7ea-bc70-4772-8f70-615444066fe9 job_description--- No description available. job_datecreated--- 2/25/2016 6:29:37 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- zzzMonthly_HLBFS_New_Manual_Set_Under_Investigation job_enabled--- False job_jobid--- 966870f7-3c50-4b3e-9d6b-5eace7da406c job_description--- No description available. job_datecreated--- 2/25/2016 6:42:09 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- zzzMonthly_HLBFS_New_Part1_SFTP_to_Validation job_enabled--- False job_jobid--- f1beb2f5-a592-40b7-b988-70aaaa163cc0 job_description--- No description available. job_datecreated--- 2/22/2016 3:03:44 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- zzzMonthly_HLBFS_New_Part2_The_SYNC job_enabled--- False job_jobid--- e1c2e66c-4fa9-4fb7-9361-81e60b34b590 job_description--- No description available. job_datecreated--- 2/25/2016 6:20:12 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- zzzMonthly_HLBFS_New_Part3_Build_BRDG job_enabled--- False job_jobid--- 7b8b0088-eeb3-46ed-9367-de79746651a0 job_description--- No description available. job_datecreated--- 11/17/2016 2:57:57 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- zzzMonthly_HLBFS_Schedule job_enabled--- False job_jobid--- d38434b3-622a-43c0-aa10-d7f04b976d78 job_description--- No description available. job_datecreated--- 4/18/2016 4:42:57 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- zzzMonthly_HLBFS_SFTP_Only job_enabled--- False job_jobid--- 23bc3320-05e2-4e04-ace8-20c2426dfa5b job_description--- No description available. job_datecreated--- 3/22/2016 7:48:00 AM job_username--- HQ\\rkmaach',
    u'job_jobname--- zzz-temp job_enabled--- False job_jobid--- 38d5635d-afef-4ca9-911c-05d59aa88d3d job_description--- No description available. job_datecreated--- 1/7/2015 8:31:37 AM job_username---',
    u'job_jobname--- zzzTEST_DEANQ_Finance_FTP job_enabled--- False job_jobid--- bf690d45-8497-4aa9-be56-ee95551ca2a8 job_description--- No description available. job_datecreated--- 7/14/2015 4:57:30 PM job_username--- HQ\\rkmaach',
    u'job_jobname--- zzzWeekly_BTSReassignClient_delete04012015 job_enabled--- False job_jobid--- 3377f7a4-4667-4d9b-9fb0-b779019353d4 job_description--- No description available. job_datecreated--- 5/15/2013 3:29:25 PM job_username--- HQ\\svcRAT',
    u'job_jobname--- zzzWeekly_BusinessUnit_Mapping_Email moved to analytics job_enabled--- False job_jobid--- bb8f70a8-f9a8-4c08-af86-a01dfad6aed9 job_description--- No description available. job_datecreated--- 11/11/2016 3:47:04 PM job_username--- HQ\\rkmaach'
]


class TestProcesses(BaseTestCase):
    def setUp(self):
        self.plugin = WinMSSQL()
        self.device = StringAttributeObject()

    def test_weird_job_names(self):
        job_line = ''
        for stdout_line in UNPACK_RESULTS:
            success = True
            if not job_line:
                job_line = stdout_line
            else:
                job_line = '\n'.join((job_line, stdout_line))
            if 'job_username---' not in stdout_line:
                continue
            try:
                self.plugin.get_job_om(StringAttributeObject(),
                                       "instance",
                                       StringAttributeObject(),
                                       'sqlserver',
                                       job_line)
            except Exception:
                success = False
            self.assertTrue(success)
            job_line = ''

    def test_cognizant(self):
        job_line = '\n'.join(COGNIZANT_RESULTS)
        job_om = self.plugin.get_job_om(StringAttributeObject(),
                                        "instance",
                                        StringAttributeObject(),
                                        "sqlserver",
                                        job_line)
        self.assertEquals(job_om.title, 'APP_Job_uspInsertShiftWasteEventsWeekly')
        self.assertEquals(job_om.enabled, 'No')
        self.assertEquals(job_om.jobid, '94c66ad2-c2fb-4425-879c-7d1f0457b11e')
        self.assertEquals(job_om.description, 'Application job : Run SP uspInsertShiftWasteEventsWeekly every Wednesday 00:10 AM')
        self.assertEquals(job_om.datecreated, '8/7/2013 12:11:46 AM')
        self.assertEquals(job_om.username, 'wwAdmin')

    def test_process(self):
        data = self.plugin.process(self.device, RESULTS, Mock())
        self.assertEquals(len(data), 6)  # Hostname, SQLInstance, SQLBackup, SQLJob, SQLDatabase, SQLAvailabilityGroup
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

        # Always On components are disabled by default, so there must be empty object map
        self.assertEquals(data[5].maps, [])

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
        job_line = '\n'.join(STDOUT_LINES[5:])
        multiline_desc_om = self.plugin.get_job_om(StringAttributeObject(),
                                                   "sqlserver",
                                                   StringAttributeObject(),
                                                   "owner_node",
                                                   job_line)
        expected = "description \n" + '\n'.join(STDOUT_LINES[6:8])
        self.assertEquals(multiline_desc_om.description, expected)

    def test_cluster_onSuccess(self):
        results = load_pickle_file(self, 'WinMSSQL_process_cluster')[0]
        data = self.plugin.process(self.device, results, Mock())
        self.assertEquals(data[1].maps[0].sql_server_version, u'13.0.4206.0')
        self.assertEquals(data[1].maps[0].cluster_node_server, 'win2016-node-02.sol-win.lab//SQLNETWORK\\CINSTANCE01')
        # should have 6 databases
        self.assertEquals(len(data[4].maps), 6)
        # should have 5 jobs
        self.assertEquals(len(data[3].maps), 5)


class TestAlwaysOnCollect(BaseTestCase):

    def setUp(self):
        self.plugin = WinMSSQL()
        self.plugin.log = Mock()
        self.device = create_ao_device_proxy()

    def check_availability_groups(self, data):

        availability_group = data.get('777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertIsNotNone(availability_group)
        self.assertEqual(availability_group['ag_res_id'], u'777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEqual(availability_group['failure_condition_level'], 3)
        self.assertEqual(availability_group['is_distributed'], False)
        self.assertEqual(availability_group['primary_replica_server_name'], u'WSC-NODE-02\\SQLAON')
        self.assertEqual(availability_group['cluster_resource_state'], 2)
        self.assertEqual(availability_group['id'], u'b6040ddd-408b-4fe5-a370-0c7c45358ca7')
        self.assertEqual(availability_group['automated_backup_preference'], 2)
        self.assertEqual(availability_group['name'], u'TestAG1')
        self.assertEqual(availability_group['db_level_health_detection'], False)
        self.assertEqual(availability_group['cluster_type'], None)
        self.assertEqual(availability_group['health_check_timeout'], 30000)

    def check_availability_replicas(self, data):

        availability_replica = data.get('b78190e7-2518-4ab8-b5ed-0cf3c4c54f9a')
        self.assertIsNotNone(availability_replica)
        self.assertEqual(availability_replica['ag_res_id'], u'0b38a4e4-8c30-46e8-873e-7cd1b397bfc1')
        self.assertEqual(availability_replica['name'], u'WSC-NODE-01\\SQLAON')
        self.assertEqual(availability_replica['replica_server_name'], u'WSC-NODE-01\\SQLAON')
        self.assertEqual(availability_replica['endpoint_url'], u'TCP://wsc-node-01.sol-win.lab:5023')
        self.assertEqual(availability_replica['ag_id'], u'd3313358-3897-492c-9e65-3e4af421e7a3')
        self.assertEqual(availability_replica['replica_server_hostname'], u'wsc-node-01')
        self.assertEqual(availability_replica['id'], u'b78190e7-2518-4ab8-b5ed-0cf3c4c54f9a')

    def check_availability_listeners(self, data):

        availability_listener = data.get('5869339c-942f-4ef1-b085-d9718db16cd3')
        self.assertIsNotNone(availability_listener)
        self.assertEqual(availability_listener['network_mode'], 1)
        self.assertEqual(availability_listener['ag_id'], u'777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEqual(availability_listener['state'], 2)
        self.assertEqual(availability_listener['name'], u'TestAG1_TestAG_Listener')
        self.assertEqual(availability_listener['tcp_port'], 1425)
        self.assertEqual(availability_listener['dns_name'], u'TestAG_Listener')
        self.assertEqual(availability_listener['ip_address'], u'10.88.123.201')
        self.assertEqual(availability_listener['id'], u'5869339c-942f-4ef1-b085-d9718db16cd3')

    def check_sql_instances(self, data):

        sql_instance = data.get('WSC-NODE-01\SQLAON')
        self.assertIsNotNone(sql_instance)
        self.assertEqual(sql_instance['sql_server_instance_full_name'], u'WSC-NODE-01\\SQLAON')
        self.assertEqual(sql_instance['sql_server_fullname'], u'WSC-NODE-01\\SQLAON')
        self.assertEqual(sql_instance['sql_server_version'], u'13.0.1601.5')
        self.assertEqual(sql_instance['instance_original_name'], u'SQLAON')
        self.assertEqual(sql_instance['is_on_wsfc'], None)
        self.assertEqual(sql_instance['sql_hostname_fqdn'], 'wsc-node-01.sol-win.lab')
        self.assertEqual(sql_instance['is_clustered_instance'], False)
        self.assertEqual(sql_instance['instance_name'], u'SQLAON')
        self.assertEqual(sql_instance['sqlhostname'], u'wsc-node-01')
        self.assertEqual(sql_instance['sql_server_name'], u'WSC-NODE-01\\SQLAON')
        self.assertEqual(sql_instance['sql_host_ip'], u'10.88.122.131')
        self.assertEqual(sql_instance['sql_server_node'], u'wsc-node-01')

    def check_availability_databases(self, data):

        availability_database = data.get(('WSC-NODE-01\\SQLAON', 5))
        self.assertIsNotNone(availability_database)
        self.assertEqual(availability_database['ag_res_id'], u'0b38a4e4-8c30-46e8-873e-7cd1b397bfc1')
        self.assertEqual(availability_database['sync_state'], 2)
        self.assertEqual(availability_database['db_id'], 5)
        self.assertEqual(availability_database['name'], u'test_alwayson_db_1')
        self.assertEqual(availability_database['lastlogbackupdate'], -62135596800)
        self.assertEqual(availability_database['createdate'], 1606976235.56)
        self.assertEqual(availability_database['systemobject'], False)
        self.assertEqual(availability_database['lastbackupdate'], 1607053473)
        self.assertEqual(availability_database['collation'], u'SQL_Latin1_General_CP1_CI_AS')
        self.assertEqual(availability_database['defaultfilegroup'], u'PRIMARY')
        self.assertEqual(availability_database['version'], 852)
        self.assertEqual(availability_database['suspended'], False)
        self.assertEqual(availability_database['adb_id'], u'69945148-b97e-4132-b9fc-e6a6a19bb6ef')
        self.assertEqual(availability_database['owner'], u'SOL-WIN\\Administrator')
        self.assertEqual(availability_database['primaryfilepath'], u'C:\\Program Files\\Microsoft SQL Server\\MSSQL13.SQLAON\\MSSQL\\DATA')
        self.assertEqual(availability_database['recoverymodel'], 1)
        self.assertEqual(availability_database['isaccessible'], True)

    if CROCHET_AVAILABLE:

        @patch('ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.WinMSSQL.SQLCommander', DummySQLCommander)
        @crochet.wait_for(timeout=5.0)
        @defer.inlineCallbacks
        def test_collect_ao_info(self):

            winrs = DummySQLCommander(None, Mock())
            conn_info = self.plugin.conn_info(self.device)
            log = Mock()

            ao_info = yield self.plugin.collect_ao_info(winrs, conn_info, DB_LOGINS, HOST_USER_NAME, HOST_USER_PASSWORD,
                                                        log)
            self.assertIsInstance(ao_info, dict)

            # Check whether all expected categories (keys) are present
            expected_ao_info_keys = {'errors', 'sql_instances', 'availability_groups', 'availability_replicas',
                                     'availability_listeners', 'availability_databases'}
            actual_ao_info_keys = set(ao_info.keys())
            self.assertEqual(expected_ao_info_keys.symmetric_difference(actual_ao_info_keys), set())

            # check exact elements quantity for each category
            ao_elements_quantity_map = {
                'errors': 0,
                'sql_instances': 5,
                'availability_groups': 3,
                'availability_replicas': 8,
                'availability_listeners': 3,
                'availability_databases': 9
            }
            for ao_element_name, ao_element_quantity in ao_elements_quantity_map.iteritems():
                self.assertEqual(len(ao_info.get(ao_element_name, -1)), ao_element_quantity)

            # check one arbitrary element from each category
            # 1. Availability Groups:
            self.check_availability_groups(ao_info.get('availability_groups'))

            # 2. Availability Replicas:
            self.check_availability_replicas(ao_info.get('availability_replicas'))

            # 3. Availability Listeners:
            self.check_availability_listeners(ao_info.get('availability_listeners'))

            # 4. SQL Instances:
            self.check_sql_instances(ao_info.get('sql_instances'))

            # 5. Availability Databases
            self.check_availability_databases(ao_info.get('availability_databases'))


class TestAlwaysOnProcesses(BaseTestCase):

    def setUp(self):
        self.plugin = WinMSSQL()
        self.device = StringAttributeObject()

    def check_ao_sql_instance_oms(self, ao_sql_instances_oms):
        self.assertIsInstance(ao_sql_instances_oms, list)
        self.assertEquals(len(ao_sql_instances_oms), 5)

        ao_sql_instances0_om = ao_sql_instances_oms[0]
        self.assertEquals(ao_sql_instances0_om.cluster_node_server, 'wsc-node-03.sol-win.lab//WSC-NODE-03\\SQLAON')
        self.assertEquals(ao_sql_instances0_om.id, 'WSC-NODE-03_SQLAON')
        self.assertEquals(ao_sql_instances0_om.instancename, u'SQLAON')
        self.assertEquals(ao_sql_instances0_om.owner_node_ip, u'10.88.122.133')
        self.assertEquals(ao_sql_instances0_om.perfmon_instance, 'MSSQL$SQLAON')
        self.assertEquals(ao_sql_instances0_om.sql_server_version, u'13.0.1601.5')
        self.assertEquals(ao_sql_instances0_om.title, u'SQLAON')

        # TODO: Add checks for other SQL Instances. Maybe negative scenario.

    def check_ao_oms(self, ag_om_list):
        self.assertEquals(len(ag_om_list), 3)

        ag0_om = ag_om_list[0]
        self.assertEquals(ag0_om.ag_res_id, u'777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEquals(ag0_om.automated_backup_preference, 'Prefer Secondary')
        self.assertEquals(ag0_om.cluster_resource_state, 2)
        self.assertEquals(ag0_om.cluster_type, 'unknown')
        self.assertEquals(ag0_om.db_level_health_detection, False)
        self.assertEquals(ag0_om.failure_condition_level, 'OnCriticalServerErrors')
        self.assertEquals(ag0_om.health_check_timeout, 30000)
        self.assertEquals(ag0_om.id, '777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEquals(ag0_om.is_distributed, False)
        self.assertEquals(ag0_om.name, u'TestAG1')
        self.assertEquals(ag0_om.set_winsqlinstance, 'WSC-NODE-02_SQLAON')
        self.assertEquals(ag0_om.title, u'TestAG1')
        self.assertEquals(ag0_om.unigue_id, u'b6040ddd-408b-4fe5-a370-0c7c45358ca7')

        # TODO: Add checks for other AGs. Maybe negative scenario.

    def check_ar_oms(self, ar_om_list):

        self.assertEquals(len(ar_om_list), 3)

        ar0_om = ar_om_list[0]
        self.assertEquals(ar0_om.ag_id, u'b6040ddd-408b-4fe5-a370-0c7c45358ca7')
        self.assertEquals(ar0_om.ag_res_id, u'777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEquals(ar0_om.endpoint_url, u'TCP://wsc-node-03.sol-win.lab:5023')
        self.assertEquals(ar0_om.id, 'd97da9be-1c80-439d-bb19-11bc5c5f5083')
        self.assertEquals(ar0_om.name, u'WSC-NODE-03\\SQLAON')
        self.assertEquals(ar0_om.replica_server_hostname, u'wsc-node-03')
        self.assertEquals(ar0_om.replica_server_name, u'WSC-NODE-03\\SQLAON')
        self.assertEquals(ar0_om.set_winsqlinstance, 'WSC-NODE-03_SQLAON')
        self.assertEquals(ar0_om.title, u'WSC-NODE-03\\SQLAON')
        self.assertEquals(ar0_om.unigue_id, u'd97da9be-1c80-439d-bb19-11bc5c5f5083')

    def check_al_oms(self, al_om_list):

        self.assertEquals(len(al_om_list), 2)

        al0_om = al_om_list[0]
        self.assertEquals(al0_om.ag_id, u'0b38a4e4-8c30-46e8-873e-7cd1b397bfc1')
        self.assertEquals(al0_om.dns_name, u'TestAG')
        self.assertEquals(al0_om.id, 'cf2628b9-d180-46e5-9e56-debf65268cd5')
        self.assertEquals(al0_om.ip_address, u'10.88.123.205')
        self.assertEquals(al0_om.name, u'TestAG_TestAG')
        self.assertEquals(al0_om.network_mode, 1)
        self.assertEquals(al0_om.state, 'Online')
        self.assertEquals(al0_om.tcp_port, 1433)
        self.assertEquals(al0_om.title, u'TestAG_TestAG')
        self.assertEquals(al0_om.unigue_id, u'cf2628b9-d180-46e5-9e56-debf65268cd5')

        # TODO: Add checks for other ALs. Maybe negative scenario.

    def check_adb_oms(self, adb_om_list):

        self.assertEquals(len(adb_om_list), 3)

        adb0_om = adb_om_list[0]
        self.assertEquals(adb0_om.ag_res_id, u'777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEquals(adb0_om.cluster_node_server, 'wsc-node-02.sol-win.lab//WSC-NODE-02\\SQLAON')
        self.assertEquals(adb0_om.collation, u'SQL_Latin1_General_CP1_CI_AS')
        self.assertEquals(adb0_om.createdate, '2020/12/04 08:40:52')
        self.assertEquals(adb0_om.db_id, 7)
        self.assertEquals(adb0_om.defaultfilegroup, u'PRIMARY')
        self.assertEquals(adb0_om.id, 'WSC-NODE-02_SQLAON7')
        self.assertEquals(adb0_om.instancename, u'SQLAON')
        self.assertEquals(adb0_om.isaccessible, True)
        self.assertEquals(adb0_om.lastbackupdate, '2020/12/04 08:40:52')
        self.assertEquals(adb0_om.lastlogbackupdate, '')
        self.assertEquals(adb0_om.name, u'test_alwayson_db_3')
        self.assertEquals(adb0_om.owner, u'sa')
        self.assertEquals(adb0_om.primaryfilepath, u'C:\\Program Files\\Microsoft SQL Server\\MSSQL13.SQLAON\\MSSQL\\DATA')
        self.assertEquals(adb0_om.recoverymodel, 1)
        self.assertEquals(adb0_om.set_winsqlavailabilityreplica, '173ce86b-abdc-4ca2-984a-ade7950c55d1')
        self.assertEquals(adb0_om.suspended, False)
        self.assertEquals(adb0_om.sync_state, 'Synchronized')
        self.assertEquals(adb0_om.systemobject, False)
        self.assertEquals(adb0_om.title, u'test_alwayson_db_3')
        self.assertEquals(adb0_om.unigue_id, u'85dc383a-bf7b-4ab7-8cea-cc52919bdb36')
        self.assertEquals(adb0_om.version, 852)

        # TODO: Add checks for other ADBs. Maybe negative scenario.

    def test_get_ao_oms(self):
        """
        WinMSSQL.get_ao_oms should return result in such format:
        {
            'oms': [
                # 0: Availability Group
                {
                    # Tuple of (ag_relname, ag_compname, ag_modname) is used for Availability Groups. Should be one
                    #  key as Availability Groups are placed under one OS component
                    ('winsqlavailabilitygroups', 'os', 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityGroup'): [
                        <ObjectMap {
                            # <Availability-Group-Properties>
                        }>
                    ]
                },
                # 1: Availability Replica
                {
                    ('winsqlavailabilityreplicas', 'os/winsqlavailabilitygroups/<Availability-Group-ID>',
                        'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityReplica'): [
                            <ObjectMap {
                            # <Availability-Replica-Properties>
                        }>
                    ]
                },
                # 2: Availability Listener
                {
                    ('winsqlavailabilitylisteners', 'os/winsqlavailabilitygroups/<Availability-Group-ID>',
                        'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityListener'): [
                        <ObjectMap {
                            # <Availability-Listener-Properties>
                        }>
                    ]
                },
                # 3: Availability Database
                {
                    ('databases', 'os/winsqlinstances/<SQL-Instance-ID>',
                        'ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase'): [
                        <ObjectMap {
                            # <Availability-Database-Properties>
                        }>
                    ]
                }
            ]
        }
        """

        self.plugin.log = Mock()
        collect_ao_results = ALWAYS_ON_COLLECT_RESULTS

        ao_oms = self.plugin.get_ao_oms(collect_ao_results,
                                        Mock())
        self.assertIsInstance(ao_oms, dict)

        oms = ao_oms.get('oms')

        # Be sure that oms key contains List with 4 elements
        self.assertIsInstance(oms, list)
        self.assertEquals(len(oms), 4)

        # 1. Availability Groups
        # First element of the list is dictionary with Availability Groups Object Maps. The dict has only one key.
        ag_oms = oms[0]
        ag_tuple_keys = ag_oms.keys()
        self.assertIsInstance(ag_tuple_keys, list)
        self.assertEquals(len(ag_tuple_keys), 1)

        ag_tuple_key = ag_tuple_keys[0]
        self.assertEquals(len(ag_tuple_key), 3)
        self.assertEquals(ag_tuple_key[0], 'winsqlavailabilitygroups')
        self.assertEquals(ag_tuple_key[1], 'os')
        self.assertEquals(ag_tuple_key[2], 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityGroup')

        ag_om_list = ag_oms[ag_tuple_key]
        self.check_ao_oms(ag_om_list)

        # 2. Availability Replicas
        ar_oms = oms[1]
        ar_tuple_keys = ar_oms.keys()
        self.assertIsInstance(ar_tuple_keys, list)
        self.assertEquals(len(ar_tuple_keys), 3)

        ar_tuple_key = ar_tuple_keys[0]
        self.assertEquals(len(ar_tuple_key), 3)

        self.assertEquals(ar_tuple_key[0], 'winsqlavailabilityreplicas')
        self.assertEquals(ar_tuple_key[1], 'os/winsqlavailabilitygroups/777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEquals(ar_tuple_key[2], 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityReplica')

        ar_om_list = ar_oms[ar_tuple_key]
        self.check_ar_oms(ar_om_list)

        # TODO: Add checks for other ARs. Consider scenario when AR is skipped due to some reasons.

        # 3. Availability Listeners
        al_oms = oms[2]
        al_tuple_keys = al_oms.keys()
        self.assertIsInstance(al_tuple_keys, list)
        self.assertEquals(len(al_tuple_keys), 3)

        al_tuple_key = al_tuple_keys[1]
        self.assertEquals(len(al_tuple_key), 3)

        self.assertEquals(al_tuple_key[0], 'winsqlavailabilitylisteners')
        self.assertEquals(al_tuple_key[1], 'os/winsqlavailabilitygroups/0b38a4e4-8c30-46e8-873e-7cd1b397bfc1')
        self.assertEquals(al_tuple_key[2], 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityListener')

        al_om_list = al_oms[al_tuple_key]
        self.check_al_oms(al_om_list)

        # 4. Availability Databases
        adb_oms = oms[3]
        adb_tuple_keys = adb_oms.keys()
        self.assertIsInstance(adb_tuple_keys, list)
        self.assertEquals(len(adb_tuple_keys), 5)

        adb_tuple_key = adb_tuple_keys[0]
        self.assertEquals(len(adb_tuple_key), 3)

        self.assertEquals(adb_tuple_key[0], 'databases')
        self.assertEquals(adb_tuple_key[1], 'os/winsqlinstances/WSC-NODE-02_SQLAON')
        self.assertEquals(adb_tuple_key[2], 'ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase')

        adb_om_list = adb_oms[adb_tuple_key]
        self.check_adb_oms(adb_om_list)

    def test_get_ao_sql_instance_oms(self):
        """
        WinMSSQL.test_get_ao_sql_instance_oms should return result in such format:
        [
            <ObjectMap {
                # <SQL-Instance-Properties>
            }>
        ]
        """
        self.plugin.log = Mock()
        collect_ao_results = ALWAYS_ON_COLLECT_RESULTS

        ao_sql_instances_oms = self.plugin.get_ao_sql_instance_oms(collect_ao_results)
        self.check_ao_sql_instance_oms(ao_sql_instances_oms)

    def test_process(self):
        data = self.plugin.process(self.device, ALWAYS_ON_COLLECT_RESULTS, Mock())

        self.assertEquals(len(data), 14)

        # 1. SQL Instances
        ao_sql_instances_rm = data[1]
        self.assertEquals(ao_sql_instances_rm.compname, 'os')
        self.assertEquals(ao_sql_instances_rm.relname, 'winsqlinstances')

        ao_sql_instances_oms = ao_sql_instances_rm.maps
        self.check_ao_sql_instance_oms(ao_sql_instances_oms)
        self.assertEquals(ao_sql_instances_oms[0].modname, 'ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance')

        # 2. Availability Groups
        ag_rm = data[2]
        self.assertEquals(ag_rm.compname, 'os')
        self.assertEquals(ag_rm.relname, 'winsqlavailabilitygroups')

        ag_oms = ag_rm.maps
        self.check_ao_oms(ag_oms)
        self.assertEquals(ag_oms[0].modname, 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityGroup')

        # 3. Availability Replicas
        ar_rm = data[3]
        self.assertEquals(ar_rm.compname, 'os/winsqlavailabilitygroups/777c50fd-348e-4686-a622-edd90a4340e1')
        self.assertEquals(ar_rm.relname, 'winsqlavailabilityreplicas')

        ar_oms = ar_rm.maps
        self.check_ar_oms(ar_oms)
        self.assertEquals(ar_oms[0].modname, 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityReplica')

        # 4. Availability Listeners
        al_rm = data[7]
        self.assertEquals(al_rm.compname, 'os/winsqlavailabilitygroups/0b38a4e4-8c30-46e8-873e-7cd1b397bfc1')
        self.assertEquals(al_rm.relname, 'winsqlavailabilitylisteners')

        al_oms = al_rm.maps
        self.check_al_oms(al_oms)
        self.assertEquals(al_oms[0].modname, 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityListener')

        # 4. Availability Databases
        adb_rm = data[9]
        self.assertEquals(adb_rm.compname, 'os/winsqlinstances/WSC-NODE-02_SQLAON')
        self.assertEquals(adb_rm.relname, 'databases')

        adb_oms = adb_rm.maps
        self.check_adb_oms(adb_oms)
        self.assertEquals(adb_oms[0].modname, 'ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase')


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestProcesses))
    suite.addTest(makeSuite(TestAlwaysOnProcesses))
    suite.addTest(makeSuite(TestAlwaysOnCollect))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
