/*##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################*/


(function(){

var ZC = Ext.ns('Zenoss.component');

function render_link(ob) {
    if (ob && ob.uid) {
        return Zenoss.render.link(ob.uid);
    } else {
        return ob;
    }
}

Ext.apply(Zenoss.render, {
    win_entityLinkFromGrid: function(obj, col, record) {
        if (!obj)
            return;
        
        if (obj.name == 'NONE')
            return;
        
        if (typeof(obj) == 'string')
            obj = record.data;
        
        if (!obj.title && obj.name)
            obj.title = obj.name;
        
        var isLink = false;
        
        if (this.refName == 'componentgrid'){
            if (this.subComponentGridPanel || this.componentType != obj.meta_type)
                isLink = true;
        } else {
            if (!this.panel || this.panel.subComponentGridPanel)
                isLink = true;
        }
        
        if (isLink) {
            return '<a href="javascript:Ext.getCmp(\'component_card\').componentgrid.jumpToEntity(\''+obj.uid+'\', \''+obj.meta_type+'\');">'+obj.title+'</a>';
        } else {
            return obj.title;
        }
    },

    emc_productEntity: function(obj) {
        if (obj && obj.uid && obj.name) {
            return Zenoss.render.link(obj.uid, undefined, obj.name);
        } else {
            return "";
        }
    }
});

ZC.WINComponentGridPanel = Ext.extend(ZC.ComponentGridPanel, {
    subComponentGridPanel: false,

    jumpToEntity: function(uid, meta_type) {
        var tree = Ext.getCmp('deviceDetailNav').treepanel;
        var tree_selection_model = tree.getSelectionModel();
        var components_node = tree.getRootNode().findChildBy(
            function(n) {
                if (n.data) {
                    return n.data.text == 'Components';
                }
                
                return n.text == 'Components';
            });
        
        var component_card = Ext.getCmp('component_card');
        
        if (components_node.data) {
            component_card.setContext(components_node.data.id, meta_type);
        } else {
            component_card.setContext(components_node.id, meta_type);
        }

        component_card.selectByToken(uid);
        var component_type_node = components_node.findChildBy(
            function(n) {
                if (n.data) {
                    return n.data.id == meta_type;
                }
                
                return n.id == meta_type;
            });
        
        if (component_type_node.select) {
            tree_selection_model.suspendEvents();
            component_type_node.select();
            tree_selection_model.resumeEvents();
        } else {
            tree_selection_model.select([component_type_node], false, true);
        }
    }
});


ZC.registerName('WinRMService', _t('Service'), _t('Services'));

ZC.WinRMServicePanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'name',
            componentType: 'WinRMService',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'servicename'},
                {name: 'startmode'},
                {name: 'state'},
                {name: 'account'},
                {name: 'monitor'},
                {name: 'locking'},
                {name: 'monitored'}
            ],
            columns: [{
                id: 'severity',
                dataIndex: 'severity',
                header: _t('Events'),
                renderer: Zenoss.render.severity,
                sortable: true,
                width: 50
            },{
                id: 'name',
                dataIndex: 'servicename',
                header: _t('Name')
            },{
                id: 'startmode',
                dataIndex: 'startmode',
                header: _t('Start Mode'),
                sortable: true,
                width: 110
            },{
                id: 'state',
                dataIndex: 'state',
                header: _t('State'),
                sortable: true,
                width: 110
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

Ext.reg('WinRMServicePanel', ZC.WinRMServicePanel);

ZC.registerName('WinRMProc', _t('Processor'), _t('Processors'));
 
ZC.WinRMProcPanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'name',
            componentType: 'WinRMProc',
            fields: [
                {name: 'uid'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'numbercore'},
                {name: 'status'},
                {name: 'severity'},
                {name: 'architecture'},
                {name: 'clockspeed'},
                {name: 'monitored'},
                {name: 'product'},
                {name: 'manufacturer'},
                {name: 'monitor'},
                {name: 'locking'},
                {name: 'monitored'}
            ],
            columns: [{
                id: 'severity',
                dataIndex: 'severity',
                header: _t('Events'),
                renderer: Zenoss.render.severity,
                sortable: true,
                width: 50
            },{
                id: 'manufacturer',
                dataIndex: 'manufacturer',
                header: _t('Manufacturer'),
                renderer: render_link
            },{
                id: 'product',
                dataIndex: 'product',
                header: _t('Model'),
                renderer: render_link
            },{
                id: 'numbercore',
                dataIndex: 'numbercore',
                header: _t('Number of Cores'),
                sortable: true,
                width: 110
            },{
                id: 'architecture',
                dataIndex: 'architecture',
                header: _t('Architecture'),
                sortable: true,
                width: 110
            },{
                id: 'clockspeed',
                dataIndex: 'clockspeed',
                header: _t('Clock Speed'),
                sortable: true,
                width: 110,
                renderer: function(x){ return x + ' MHz';}
            },{
                id: 'status',
                dataIndex: 'status',
                header: _t('Status'),
                sortable: true,
                width: 110
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
        ZC.WinRMProcPanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('WinRMProcPanel', ZC.WinRMProcPanel);

})();