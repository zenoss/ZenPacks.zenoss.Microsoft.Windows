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

/* WinRS Datasource UI ******************************************************/

Zenoss.form.WinRSStrategy = Ext.extend(Ext.Panel, {
    constructor: function(config) {
        config = config || {};
        var record = config.record;

        Ext.apply(config, {
            border: false,
            items:[{
                xtype: 'combo',
                width: 300,
                fieldLabel: _t('Strategy'),
                name: 'strategy',
                ref: 'StrategyCombo',
                allowBlank: false,
                editable: false,
                value: record.strategy,
                triggerAction: 'all',
                listeners: {
                    select: this.updateFormFields,
                    scope: this
                },
                queryMode: 'local',
                displayField: 'strategy',
                store: record.availableStrategies
            },{
                xtype: 'textfield',
                width: 300,
                fieldLabel: _t('Resource'),
                name: 'resource',
                ref: 'ResourceTextfield',
                value: record.resource,
                hidden: record.strategy == 'Custom Command'
            },{
                xtype: 'parser',
                width: 279,
                fieldLabel: _t('Parser'),
                name: 'parser',
                ref: 'ParserCombo',
                value: record.parser,
                record: record,
                hidden: record.strategy != 'Custom Command'
            },{
                xtype: 'checkbox',
                fieldLabel: _t('Use Powershell'),
                name: 'usePowershell',
                ref: 'UsePowershellCheckbox',
                checked: record.usePowershell,
                hidden: record.strategy != 'Custom Command'
            },{
                xtype: 'textarea',
                width: 300,
                fieldLabel: _t('Script'),
                name: 'script',
                ref: 'ScriptTextarea',
                value: record.script,
                hidden: record.strategy != 'Custom Command'
            }]
        });
        
        Zenoss.form.WinRSStrategy.superclass.constructor.apply(this, arguments);
    },
    
    updateFormFields: function() {
        if (this.StrategyCombo.value == 'Custom Command') {
            this.ResourceTextfield.hide();
            this.ParserCombo.show();
            this.UsePowershellCheckbox.show();
            this.ScriptTextarea.show();
        }
        else {
            this.ResourceTextfield.show();
            this.ParserCombo.hide();
            this.UsePowershellCheckbox.hide();
            this.ScriptTextarea.hide();
        }
    }
});

// Ext.version will be defined in ExtJS3 and undefined in ExtJS4.
if (Ext.version === undefined) {
    Ext.reg('winrsstrategy', 'Zenoss.form.WinRSStrategy');
} else {
    Ext.reg('winrsstrategy', Zenoss.form.WinRSStrategy);
}

}());
