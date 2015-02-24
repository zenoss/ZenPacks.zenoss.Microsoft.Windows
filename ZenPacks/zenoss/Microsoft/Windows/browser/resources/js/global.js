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
ZC.registerName('WinDBInstance', _t('MSSQL Instance'), _t('MSSQL Instances'));
ZC.registerName('WinDatabase', _t('MSSQL Database'), _t('MSSQL Databases'));
ZC.registerName('WinBackupDevice', _t('MSSQL Backup Device'), _t('MSSQL Backup Devices'));
ZC.registerName('WinSQLJob', _t('MSSQL Job'), _t('MSSQL Jobs'));
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
                width: 279,
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
                height: 200,
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

var DEVICE_SUMMARY_PANEL = 'deviceoverviewpanel_summary';

Ext.ComponentMgr.onAvailable(DEVICE_SUMMARY_PANEL, function(){
    var summarypanel = Ext.getCmp(DEVICE_SUMMARY_PANEL);
    if (Zenoss.env.device_uid.search('/Server/Microsoft') != -1){
        summarypanel.removeField('memory');
        summarypanel.addField({
            xtype: 'displayfield',
            id: 'memory-displayfield',
            name: 'memory',
            fieldLabel: _t('Physical/Total Virtual Memory')
        });
    }

var check_datapoint_name = false;

var handler_timeout = setInterval(function(){
    var dp_dialog = Ext.getCmp("addDataPointDialog");

    // Check if need to restart check_dp_name setInterval
    if(!dp_dialog && !check_datapoint_name){
        check_datapoint_name = setInterval(function(){ check_dp_name() }, 1000);
    }

    // Check if dialog window is appeared
    if(dp_dialog){
        var field = Ext.getCmp('metricName');
        submit_bt = Ext.getCmp('addDataPointDialog').query('DialogButton')[0];

        if(field.getValue()){
            if(field.getEl().getAttribute('isEqual') === 'true'){
                submit_bt.setDisabled(false);
                Ext.getCmp('metricName').clearInvalid();
            } else {
                submit_bt.setDisabled(true);
                field.markInvalid('The name chosen for Data Point must be the same as the Data Source');
            }
        }
    }
}, 500);

var check_dp_name = function(){
    var dp_dialog = Ext.getCmp("addDataPointDialog");

    // Check if dialog window is appeared
    if(dp_dialog){

        // Clear interval
        clearInterval(check_datapoint_name);
        check_datapoint_name = false;

        var grid = Ext.getCmp('dataSourceTreeGrid');
        // Getting selected Data Source
        var selectedNode = grid.getSelectionModel().getSelectedNode();

        // Getting Data point filed
        var field = Ext.getCmp('metricName');
        field.getEl().set({isEqual: true});

        if(selectedNode.data.type == "Windows Perfmon"){
            // Getting Data Source name
            var ds_name = selectedNode.data.name;

            // Submit button
            submit_bt = Ext.getCmp('addDataPointDialog').query('DialogButton')[0];
            // Cancel button
            cancel_bt = Ext.getCmp('addDataPointDialog').query('DialogButton')[1];

            submit_bt.on('click', function(e){
                // Getting inserted Data Point name
                if(field.getValue() != ds_name){
                    Ext.getCmp('metricName').focus(false, 300);
                    new Zenoss.dialog.ErrorDialog({message: _t('The name chosen for Data Point must be the same as the Data Source')});
                    return false;
                } else {
                    if(!check_datapoint_name){
                        check_datapoint_name = setInterval(function(){ check_dp_name() }, 1000);
                    }
                }
            });

            cancel_bt.on('click', function(e){
                if(!check_datapoint_name){
                    check_datapoint_name = setInterval(function(){ check_dp_name() }, 1000);
                }
            });

            field.getEl().on('keyup', function (el, e) {
                field.getEl().set({isEqual: false});
                if(field.getValue() != ds_name ){
                    field.getEl().set({isEqual: false});
                } else {
                    field.getEl().set({isEqual: true});
                }
            });
        }
    }
}

});
