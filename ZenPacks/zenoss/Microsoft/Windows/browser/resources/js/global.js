/*****************************************************************************
 *
 * Copyright (C) Zenoss, Inc. 2013, all rights reserved.
 *
 * This content is made available according to terms specified in
 * License.zenoss under the directory where your Zenoss product is installed.
 *
 ****************************************************************************/

(function(){

var ZC = Ext.ns('Zenoss.component');

/* Friendly Names for Component Types ***************************************/

ZC.registerName('WinRMService', _t('Service'), _t('Services'));
ZC.registerName('WinRMIIS', _t('IIS Site'), _t('IIS Sites'));
ZC.registerName('WinDBInstance', _t('Database Instance'), _t('DB Instances'));
ZC.registerName('WinDatabase', _t('Database'), _t('Databases'));
ZC.registerName('WinBackupDevice', _t('DB Backup Device'), _t('DB Backup Devices'));
ZC.registerName('WinSQLJob', _t('DB Job'), _t('DB Jobs'));
ZC.registerName('MSClusterService', _t('Cluster Service'), _t('Cluster Services'));
ZC.registerName('MSClusterResource', _t('Cluster Resource'), _t('Cluster Resources'));
ZC.registerName('WinTeamInterface', _t('Team Interface'), _t('Team Interfaces'));
ZC.registerName('WindowsInterface', _t('Interface'), _t('Interfaces'));
ZC.registerName('WindowsCPU', _t('Processor'), _t('Processors'));

}());
