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
};
var ERROR_MESSAGE = "ERROR: Invalid connection string!";

Ext.ns('Zenoss.form');

/* Ext.version will be defined in ExtJS3 and undefined in ExtJS4. */
/* Ext.panel throws an error in ExtJS3. */
if (Ext.version === undefined) {
/* zDBInstances property */
Zenoss.form.InstanceCredentials = Ext.extend(Ext.panel.Panel, {
    constructor: function(config) {
        var me = this;
        config.width = 450;
        config = Ext.applyIf(config || {}, {
            title: _t("DB Instances (leave user/password blank to use Windows authentication)"),
            id: 'creds',
            layout: 'fit',
            listeners: {
                afterrender: function() {
                    this.setValue(config.value);
                },
                scope: this
            },
            items: [ {
                xtype: 'hidden',
                name: config.name,
                itemId: 'hiddenInput',
                value: config.value
            },{
                xtype: 'grid',
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
                width: 450,

                tbar: [{
                    itemId: 'instance',
                    xtype: "textfield",
                    ref: "editConfig",
                    scope: this,
                    width: 90,
                    emptyText:'DB Instance'
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
                        var instance = this.down("textfield[itemId='instance']");
                        var user = this.down("textfield[itemId='user']");
                        var passwd = this.down("textfield[itemId='passwd']");
                        var grid = this.down('grid');
                        var value = {
                            'instance': instance.getValue(),
                            'user': user.getValue(),
                            'passwd': passwd.getValue()
                        };
                        if (instance.value) {
                            grid.getStore().add({value: value});
                        }

                        instance.setValue("");
                        user.setValue("");
                        passwd.setValue("");
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
        Zenoss.form.InstanceCredentials.superclass.constructor.apply(this, arguments);
    },
    updateHiddenField: function() {
        this.down('hidden').setValue(this.getValue());        
    },
    // --- Value handling ---
    setValue: function(values) {
        var grid = this.down('grid');
        if(typeof values != 'string'){
            values = '[{"instance":"MSSQLSERVER","user":"","passwd":""}]';
        }

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


Zenoss.zproperties.registerZPropertyType('instancecredentials', {
    xtype: 'instancecredentials'
});
Ext.reg('instancecredentials', 'Zenoss.form.InstanceCredentials');
} else {
    // The form does not work in ExtJS3
    // Ext.reg('instancecredentials', Zenoss.form.InstanceCredentials);
}

/* Zenoss.ConfigProperty.Grid */
/* Render zDBInstances property on the grid */
var zDBInstancesRender = function(value) {
    var result = [];
    try {
         if (typeof value == 'string'){
            var v = JSON.parse(value);
            Ext.each(v, function(val) {
                result.push(val.instance + ":" + val.user + ":" + "*".repeat(
                    val.passwd.length));
            });
         } else {
            result.push("MSSQLSERVER::");
         }
    } catch (err) {
        result.push(ERROR_MESSAGE);
    }
    return result.join(';');
};

/* Find a velue column and override a renderer for it */
var overrideRenderer = function(configpanel, columns) {
    var value_column = false;
    for (el in columns) {
        if ((/^value/).test(columns[el].dataIndex)) {
            value_column = columns[el];
        }
    }
    if (!value_column) {
        return false;
    }
    // make backup for the existing renderer
    // done in configpanel to maintain a proper 'this'
    configpanel.rend_func = value_column.renderer;
    // override renderer
    value_column.renderer = function(v, row, record){
        // renderer for zDBInstances
        if ((record.internalId == 'zDBInstances' || record.id == 'zDBInstances')
            && record.get('value') !== "") {
            return zDBInstancesRender(record.get('value'));
        }
        try {
            // return the default renderer vor the value
            return configpanel.rend_func(v, row, record);
        } catch (err) {
            return v;
        }
    };
};

/* Override function for configpanel */
var panelOverride = function(configpanel) {
    try {
        if (Ext.version === undefined) {
            var columns = configpanel.configGrid.columns;
            overrideRenderer(configpanel, columns);
        } else {
            /* workaround for zenoss 4.1.1 */
            var columns = configpanel.items[0].colModel.columns;
            overrideRenderer(configpanel, columns);
        }
    } catch (err) {}
};

/* Zenoss.ConfigProperty.Grid override (for device) */
Ext.ComponentMgr.onAvailable('device_config_properties', function(){
    var configpanel = Ext.getCmp('device_config_properties');
    panelOverride(configpanel);
});

/* Zenoss.ConfigProperty.Grid override (for zenoss details) */
Ext.ComponentMgr.onAvailable('configuration_properties', function(){
    var configpanel = Ext.getCmp('configuration_properties');
    panelOverride(configpanel);
});

}());
