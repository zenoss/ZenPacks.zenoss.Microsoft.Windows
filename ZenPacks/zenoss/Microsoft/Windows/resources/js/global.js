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

Ext.define("Zenoss.component.WinRMServicePanel", {
    alias:['widget.WinRMServicePanel'],
    extend:"Zenoss.component.ComponentGridPanel",
    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'caption',
            componentType: 'WinRMService',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'status'},
                {name: 'name'},
                {name: 'meta_type'},
                {name: 'locking'},
                {name: 'usesMonitorAttribute'},
                {name: 'monitor'},
                {name: 'monitored'},
                {name: 'caption'},
                {name: 'startMode'},
                {name: 'startName'},
                {name: 'serviceClassUid'}
            ],
            columns: [{
                id: 'severity',
                dataIndex: 'severity',
                header: _t('Events'),
                renderer: Zenoss.render.severity,
                sortable: true,
                width: 60
            },{
                id: 'name',
                dataIndex: 'name',
                header: _t('Service Name'),
                sortable: true,
                flex: 1,
                renderer: Zenoss.render.WinServiceClass
            },{
                id: 'caption',
                dataIndex: 'caption',
                header: _t('Caption'),
                sortable: true
            },{
                id: 'startmode',
                dataIndex: 'startMode',
                header: _t('Start Mode'),
                sortable: true,
                width: 110
            },{
                id: 'startName',
                dataIndex: 'startName',
                header: _t('Start Name'),
                widht: 110,
                sortable: true
            },{
               id: 'status',
                dataIndex: 'status',
                header: _t('Status'),
                renderer: Zenoss.render.pingStatus,
                width: 60
            },{
                id: 'monitored',
                dataIndex: 'monitored',
                header: _t('Monitored'),
                renderer: Zenoss.render.checkbox,
                sortable: true,
                width: 65
            },{
                id: 'locking',
                dataIndex: 'locking',
                header: _t('Locking'),
                renderer: Zenoss.render.locking_icons
            }]
        });
        ZC.WinRMServicePanel.superclass.constructor.call(this, config);
    }
});

ZC.registerName('WinRMService', _t('Windows Service'), _t('Windows Services'));


/* WinRS Datasource UI ******************************************************/

Zenoss.form.WinRSStrategy = Ext.extend(Ext.Panel, {
    constructor: function(config) {
        config = config || {};
        var record = config.record;
        var textareaLabel = _t('Script');
        var textareaEmptyText = _t('Powershell or DOS command');
        if (record.strategy == 'DCDiag') {
            textareaLabel = _t('Test Parameters');
            textareaEmptyText = _t('DCDiag test parameters');
        }

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
                fieldLabel: textareaLabel,
                name: 'script',
                ref: 'ScriptTextarea',
                value: record.script,
                emptyText: textareaEmptyText,
                hidden: (record.strategy != 'Custom Command' && record.strategy != 'DCDiag')
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
            this.ScriptTextarea.labelEl.update('Script');
            this.ScriptTextarea.emptyText = _t('Powershell or DOS command');
            this.ScriptTextarea.applyEmptyText();
        }
        else if (this.StrategyCombo.value == 'DCDiag') {
            this.ResourceTextfield.show();
            this.ParserCombo.hide();
            this.UsePowershellCheckbox.hide();
            this.ScriptTextarea.show();
            this.ScriptTextarea.labelEl.update('Test Parameters');
            this.ScriptTextarea.emptyText = _t('DCDiag test parameters');
            this.ScriptTextarea.applyEmptyText();
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

(function(){

var ERROR_MESSAGE = "ERROR: Invalid port/description!";

Zenoss.form.PortCheck = Ext.extend(Ext.panel.Panel, {
    constructor: function(config) {
        var me = this;
        config = Ext.applyIf(config || {}, {
            title: _t("Ports to test if listening."),
            id: 'windowsPortScan',
            layout: 'fit',
            listeners: {
                afterrender: function() {
                    this.setValue(config.record.ports);
                },
                scope: this
            },
            items: [ {
                xtype: 'hidden',
                name: 'ports',
                itemId: 'hiddenInput',
                value: config.record.ports
            },{
                xtype: 'grid',
                width: 500,
                hideHeaders: true,
                columns: [{
                    dataIndex: 'value',
                    flex: 1,
                    renderer: function(value) {
                        try {
                            return Ext.String.format(
                                "{0}:{1}", value.port, value.desc
                            );
                        } catch (err) {
                            return ERROR_MESSAGE;
                        }
                    }
                }],

                store: {
                    fields: ['value'],
                    data: []
                },

                height: this.height || 200,
                width: 500,

                tbar: [{
                    itemId: 'port',
                    xtype: "numberfield",
                    ref: "editConfig",
                    scope: this,
                    width: 60,
                    emptyText:'Port #'
                },{
                    itemId: 'desc',
                    xtype: "textfield",
                    scope: this,
                    width: 120,
                    emptyText:'Description',
                    value: '' //to avoid undefined value
                },{
                    text: 'Add',
                    scope: this,
                    handler: function() {
                        var port = this.down("textfield[itemId='port']");
                        var desc = this.down("textfield[itemId='desc']");
                        var grid = this.down('grid');
                        var value = {
                            'port': port.getValue(),
                            'desc': desc.getValue(),
                        };
                        if (port.value) {
                            var canAdd = true;
                            grid.getStore().each(function(record){
                                if (record.get('value').port == port.value) {
                                    canAdd = false;
                                }
                            });
                            if (!canAdd){
                                new Zenoss.dialog.ErrorDialog({message: _t('Port {port} already being tested.  Please enter a unique port number.'.replace("{port}",port.value))});
                                return false;
                            }
                            grid.getStore().add({value: value});
                        }

                        port.setValue("");
                        desc.setValue("");
                        this.updateHiddenField();
                    }
                },{
                    text: "Remove",
                    itemId: 'removeButton',
                    disabled: true, // initial state
                    scope: this,
                    handler: function() {
                        var grid = this.down('grid'),
                            selModel = grid.getSelectionModel(),
                            store = grid.getStore();
                        store.remove(selModel.getSelection());
                        this.updateHiddenField();
                    }
                }],

                listeners: {
                    scope: this,
                    selectionchange: function(selModel, selection) {
                        var removeButton = me.down('button[itemId="removeButton"]');
                        removeButton.setDisabled(Ext.isEmpty(selection));
                    }
                }
            }]
        });
        Zenoss.form.PortCheck.superclass.constructor.apply(this, arguments);
    },
    updateHiddenField: function() {
        this.down('hidden').setValue(this.getValue());
    },
    // --- Value handling ---
    setValue: function(values) {
        var grid = this.down('grid');

        var data = [];
        try {
            values = JSON.parse(values);

            if (values) {
                Ext.each(values, function(value) {
                    data.push({value: value});
                });
            }
            grid.getStore().loadData(data);
        } catch(e) {}
    },

    getValue: function() {
        var grid = this.down('grid');
        var data = [];
        grid.getStore().each(function(record) {
            data.push(record.get('value'));
        });
        return JSON.stringify(data);
    }
});

// Ext.version will be defined in ExtJS3 and undefined in ExtJS4.
if (Ext.version === undefined) {
    Ext.reg('portcheck', 'Zenoss.form.PortCheck');
} else {
    Ext.reg('portcheck', Zenoss.form.PortCheck);
}

}());


(function(){

Zenoss.form.StartModeGroup = Ext.extend(Ext.panel.Panel, {
         constructor: function(config) {
             width = 300;
             var auto = false;
             if (config.record.startmode.indexOf('Auto') > -1) {
                 auto = true;
             }
             var manual = false;
             if (config.record.startmode.indexOf('Manual') > -1) {
                 manual = true;
             }
             var disabled = false;
             if (config.record.startmode.indexOf('Disabled') > -1) {
                 disabled = true;
             }
             config = Ext.applyIf(config || {}, {
                 layout: 'fit',
                   listeners: {
                        afterrender: function() {
                            if (config.record.startmode){
                                this.setValue(config.record.startmode.split(','));
                            }
                        },
                        scope: this
                 },
                 items: [ {
                     xtype: 'hidden',
                     name: 'startmode',
                     itemId: 'hiddenInput',
                     value: config.record.startmode
                 },{
                     xtype: 'checkboxgroup',
                     itemId: 'checkboxgroup',
                     columns: 1,
                     vertical: true,
                     listeners: {
                         change: function() { this.updateHiddenField();
                         },
                         scope: this
                     },
                     items: [{boxLabel: 'Auto', name: 'autostart', inputValue: 'Auto', checked: auto},
                             {boxLabel: 'Manual', name: 'manualstart', inputValue: 'Manual', checked: manual},
                             {boxLabel: 'Disabled', name: 'disabledstart', inputValue: 'Disabled', checked: disabled}]
                 },]
             });
             Zenoss.form.StartModeGroup.superclass.constructor.apply(this, arguments);
         },
         updateHiddenField: function() {
             this.down('hidden').setValue(this.getValue());
         },
         // --- Value handling ---
         setValue: function(values) {
             var group = this.down('checkboxgroup');
             var auto = false;
             if (values.indexOf('Auto') > -1) {
                 auto = true;
             }
             var manual = false;
             if (values.indexOf('Manual') > -1) {
                 manual = true;
             }
             var disabled = false;
             if (values.indexOf('Disabled') > -1) {
                 disabled = true;
             }
             if (group) {
                 group.setValue({autostart: auto, manualstart: manual, disabledstart: disabled});
             }
         },
         // --- Value handling ---
         getValue: function() {
             var group = this.down("checkboxgroup");
             if (group != null){
             var startmodes = ['None',];
             groupValues = group.getValue();
             if (groupValues.hasOwnProperty('autostart')) {
                 startmodes.push(groupValues.autostart);
             }
             if (groupValues.hasOwnProperty('manualstart')) {
                 startmodes.push(groupValues.manualstart);
             }
             if (groupValues.hasOwnProperty('disabledstart')) {
                 startmodes.push(groupValues.disabledstart);
             }
             if (startmodes.length > 1){
                 startmodes.splice(startmodes.indexOf('None'),1);
             }
             return startmodes.toString();
             }
         }

     });

    // Ext.version will be defined in ExtJS3 and undefined in ExtJS4.
    if (Ext.version === undefined) {
        Ext.reg('startmodegroup', 'Zenoss.form.StartModeGroup');
    } else {
        Ext.reg('startmodegroup', Zenoss.form.StartModeGroup);
    }
})();

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
