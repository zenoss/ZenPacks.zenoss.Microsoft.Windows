/*****************************************************************************
 *
 * Copyright (C) Zenoss, Inc. 2013, all rights reserved.
 *
 * This content is made available according to terms specified in
 * License.zenoss under the directory where your Zenoss product is installed.
 *
 ****************************************************************************/
(function(){

/* Helper function to get the number of stars returned for password */
String.prototype.repeat = function(num) {
    return new Array(isNaN(num)? 1 : ++num).join(this);
}
ERROR_MESSAGE = "ERROR: Invalid connection string!";

Ext.ns('Zenoss.form');

/* zDBInstances property */
Zenoss.form.InstanceCredentials = Ext.extend(Ext.form.TextField, {
    constructor: function(config) {
        config = Ext.applyIf(config || {}, {
            editable: true,
            allowBlank: true,
            submitValue: true,
            triggerAction: 'all',
        });
        config.fieldLabel = "DB Instances";
        Zenoss.form.InstanceCredentials.superclass.constructor.apply(this, arguments);
    },

    initComponent: function() {
        this.grid = this.childComponent = Ext.create('Ext.grid.Panel', {
            hideHeaders: true,
            columns: [{
                dataIndex: 'value',
                flex: 1,
                renderer: function(value) {
                    try {
                        return Ext.String.format(
                            "{0}:{1}:{2}", value.instance, value.user, "*".repeat(value.passwd.length)
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

            height: this.height || 150,
            width: 350,
            
            tbar: [{
                itemId: 'instance',
                xtype: "textfield",
                scope: this,
                width: 90,
                emptyText:'DB Instance',
            },{
                itemId: 'user',
                xtype: "textfield",
                scope: this,
                width: 70,
                emptyText:'User',
                value: '' //to avoid undefined value
            },{
                itemId: 'passwd',
                xtype: "password",
                scope: this,
                width: 80,
                emptyText:'Password',
                value: '' //to avoid undefined value
            },{
                text: 'Add',
                scope: this,
                handler: function() {
                    var instance = this.grid.down('#instance');
                    var user = this.grid.down('#user');
                    var passwd = this.grid.down('#passwd');

                    var value = {
                        'instance': instance.value,
                        'user': user.value, 
                        'passwd': passwd.value
                    };
                    if (instance.value) {
                        this.grid.getStore().add({value: value});
                    }

                    instance.setValue("");
                    user.setValue("");
                    passwd.setValue("");

                    this.checkChange();
                }
            },{
                text: "Remove",
                itemId: 'removeButton',
                disabled: true, // initial state
                scope: this,
                handler: function() {
                    var grid = this.grid,
                        selModel = grid.getSelectionModel(),
                        store = grid.getStore();
                    store.remove(selModel.getSelection());
                    this.checkChange();
                }
            }],

            listeners: {
                scope: this,
                selectionchange: function(selModel, selection) {
                    var removeButton = this.grid.down('#removeButton');
                    removeButton.setDisabled(Ext.isEmpty(selection));
                }
            }
        });
        Zenoss.form.InstanceCredentials.superclass.initComponent.call(this);
    },

    // --- Rendering ---
    // Generates the child component markup
    getSubTplMarkup: function() {
        // generateMarkup will append to the passed empty array and return it
        var buffer = Ext.DomHelper.generateMarkup(this.childComponent.getRenderTree(), []);
        // but we want to return a single string
        return buffer.join('');
    },

    // Regular containers implements this method to call finishRender for each of their
    // child, and we need to do the same for the component to display smoothly
    finishRenderChildren: function() {
        this.callParent(arguments);
        this.childComponent.finishRender();
    },

    // --- Resizing ---
    onResize: function(w, h) {
        this.callParent(arguments);
        this.childComponent.setSize(w - this.getLabelWidth(), h);
    },

    // --- Value handling ---
    setValue: function(values) {
        var data = [];
        try {
            values = JSON.parse(values);
        
            if (values) {
                Ext.each(values, function(value) {
                    data.push({value: value});
                });
            }
            this.grid.getStore().loadData(data);
        } catch(e) {}
    },

    getValue: function() {
        var data = [];
        this.grid.getStore().each(function(record) {
            data.push(record.get('value'));
        });
        return JSON.stringify(data);
    },

    getSubmitValue: function() {
        return this.getValue();
    }
});

/* Ext.version will be defined in ExtJS3 and undefined in ExtJS4. */
if (Ext.version === undefined) {
    Zenoss.zproperties.registerZPropertyType('instancecredentials', {
        xtype: 'instancecredentials',
    });
    Ext.reg('instancecredentials', 'Zenoss.form.InstanceCredentials');
} else {
    // The form does not work in ExtJS3
    // Ext.reg('instancecredentials', Zenoss.form.InstanceCredentials);
}

/* Zenoss.ConfigProperty.Grid */
/* Render zDBInstances property on the grid */
zDBInstancesRender = function(value) {
    result = [];
    try {
        var v = JSON.parse(value);
        Ext.each(v, function(val) {
            result.push(val.instance + ":" + val.user + ":" + "*".repeat(val.passwd.length));
        });
    } catch (err) {
        result.push(ERROR_MESSAGE);
    }
    return result.join(';');
}

/* Override function for configpanel */
panelOverride = function(configpanel, gridID) {
    try {
    var columns = configpanel.configGrid.columns;
    for (var el in columns) {
        if (columns[el].id === 'value') {
            // make backup for the existing renderer
            // done in configGrid to maintain a proper 'this'
            configpanel.configGrid.rend_func = columns[el].renderer;
            // override renderer
            columns[el].renderer = function(v, row, record){
                // renderer for zDBInstances
                if (record.internalId == 'zDBInstances' && record.get('value') !== "") {
                    return zDBInstancesRender(record.get('value'));
                }
                try {
                    // return the default renderer vor the value
                    return configpanel.configGrid.rend_func(v, row, record);
                } catch (err) {
                    return v;
                }
            }
        }
    }
    } catch (err) {
        try {
        /* workaround for zenoss 4.1.1 */
        var configGrid = Ext.getCmp(gridID);
        var columns = configGrid.colModel.columns;
        // var columns = configpanel.items[0].colModel.columns;
        for (var el in columns) {
            if (columns[el].id === 'value') {
                // make backup for the existing renderer
                var rend_func = columns[el].renderer;
                // override renderer
                columns[el].renderer = function(v, row, record){
                    // renderer for zDBInstances
                    if (record.id == 'zDBInstances' && record.get('value') !== "") {
                        return zDBInstancesRender(record.get('value'));
                    }
                    try {
                        // return the default renderer vor the value
                        return rend_func(v, row, record);
                    } catch (err) {
                        return v;
                    }
                }
            }
        }
        } catch (err) {}
    }
}

/* Zenoss.ConfigProperty.Grid override (for device) */
Ext.ComponentMgr.onAvailable('device_config_properties', function(){
    var configpanel = Ext.getCmp('device_config_properties');
    panelOverride(configpanel, 'ext-comp-1112');
});

/* Zenoss.ConfigProperty.Grid override (for zenoss details) */
Ext.ComponentMgr.onAvailable('configuration_properties', function(){
    var configpanel = Ext.getCmp('configuration_properties');
    panelOverride(configpanel, 'ext-comp-1157');
});

}());
