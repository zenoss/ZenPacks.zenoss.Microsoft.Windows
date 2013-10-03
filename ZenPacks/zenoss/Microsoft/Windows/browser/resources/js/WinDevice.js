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

    win_productEntity: function(obj) {
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
            autoExpandColumn: 'displayname',
            componentType: 'WinRMService',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'servicename'},
                {name: 'caption'},
                {name: 'startmode'},
                {name: 'state'},
                {name: 'account'},
                {name: 'usesMonitorAttribute'},
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
                header: _t('Name'),
                sortable: true,
                width: 110
            },{
                id: 'displayname',
                dataIndex: 'caption',
                header: _t('Display Name'),
                sortable: true
            },{
                id: 'startmode',
                dataIndex: 'startmode',
                header: _t('Start Mode'),
                sortable: true,
                width: 110
            },{
                id: 'state',
                dataIndex: 'state',
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
        ZC.WinRMServicePanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('WinRMServicePanel', ZC.WinRMServicePanel);

ZC.registerName('WinRMProc', _t('Processor'), _t('Processors'));
 
ZC.WinRMProcPanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'product',
            componentType: 'WinRMProc',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'numbercore'},
                {name: 'status'},
                {name: 'architecture'},
                {name: 'clockspeed'},
                {name: 'product'},
                {name: 'manufacturer'},
                {name: 'usesMonitorAttribute'},
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

ZC.registerName('WinRMIIS', _t('IIS Site'), _t('IIS Sites'));

ZC.WinRMIISPanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'displayname',
            componentType: 'WinRMIIS',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'sitename'},
                {name: 'caption'},
                {name: 'apppool'},
                {name: 'status'},
                {name: 'usesMonitorAttribute'},
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
                dataIndex: 'sitename',
                header: _t('Name'),
                sortable: true,
                width: 110
            },{
                id: 'displayname',
                dataIndex: 'caption',
                header: _t('Caption Name'),
                sortable: true
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
        ZC.WinRMIISPanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('WinRMIISPanel', ZC.WinRMIISPanel);


ZC.registerName('WinDBInstance', _t('Database Instance'), _t('DB Instances'));

ZC.WinDBInstancePanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'instancename',
            componentType: 'WinDBInstance',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'instancename'},
                {name: 'backupdevices'},
                {name: 'roles'},
                {name: 'usesMonitorAttribute'},
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
                id: 'instancename',
                dataIndex: 'instancename',
                header: _t('Instance Name'),
                sortable: true
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
        ZC.WinDBInstancePanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('WinDBInstancePanel', ZC.WinDBInstancePanel);

ZC.registerName('WinDatabase', _t('Database'), _t('Databases'));

ZC.WinDatabasePanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'name',
            componentType: 'WinDatabase',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'instancename'},
                {name: 'instance'},
                {name: 'version'},
                {name: 'owner'},
                {name: 'lastbackup'},
                {name: 'lastlogbackup'},
                {name: 'isaccessible'},
                {name: 'collation'},
                {name: 'dbcreatedate'},
                {name: 'defaultfilegroup'},
                {name: 'databaseguid'},
                {name: 'primaryfilepath'},
                {name: 'usesMonitorAttribute'},
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
                dataIndex: 'title',
                header: _t('Name'),
                sortable: true
            },{
                id: 'instance',
                dataIndex: 'instance',
                header: _t('Instance Name'),
                renderer: Zenoss.render.win_entityLinkFromGrid,
                sortable: true,
                width: 200
            },{
                id: 'owner',
                dataIndex: 'owner',
                header: _t('Owner'),
                sortable: true
            },{
                id: 'collation',
                dataIndex: 'collation',
                header: _t('Collation'),
                sortable: true,
                width: 180
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
        ZC.WinDatabasePanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('WinDatabasePanel', ZC.WinDatabasePanel);

ZC.registerName('WinBackupDevice', _t('DB Backup Device'), _t('DB Backup Devices'));

ZC.WinBackupDevicePanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'title',
            componentType: 'WinBackupDevice',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'instancename'},
                {name: 'instance'},
                {name: 'devicetype'},
                {name: 'physicallocation'},
                {name: 'status'},
                {name: 'usesMonitorAttribute'},
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
                id: 'title',
                dataIndex: 'title',
                header: _t('Name'),
                sortable: true
            },{
                id: 'instance',
                dataIndex: 'instance',
                header: _t('Instance Name'),
                sortable: true,
                renderer: Zenoss.render.win_entityLinkFromGrid,
                width: 200
            },{
                id: 'devicetype',
                dataIndex: 'devicetype',
                header: _t('Device Type'),
                sortable: true,
                width: 180
            },{
                id: 'status',
                dataIndex: 'status',
                header: _t('Status'),
                sortable: true,
                width: 100
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
        ZC.WinBackupDevicePanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('WinBackupDevicePanel', ZC.WinBackupDevicePanel);

ZC.registerName('WinSQLJob', _t('DB Job'), _t('DB Jobs'));

ZC.WinSQLJobPanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'title',
            componentType: 'WinSQLJob',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'instancename'},
                {name: 'instance'},
                {name: 'description'},
                {name: 'enabled'},
                {name: 'jobid'},
                {name: 'usesMonitorAttribute'},
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
                id: 'title',
                dataIndex: 'title',
                header: _t('Name'),
                sortable: true
            },{
                id: 'instance',
                dataIndex: 'instance',
                header: _t('Instance Name'),
                sortable: true,
                renderer: Zenoss.render.win_entityLinkFromGrid,
                width: 200
            },{
                id: 'enabled',
                dataIndex: 'enabled',
                header: _t('Enabled'),
                sortable: true,
                width: 180
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
        ZC.WinSQLJobPanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('WinSQLJobPanel', ZC.WinSQLJobPanel);

ZC.registerName('MSClusterService', _t('Cluster Service'), _t('Cluster Services'));

ZC.MSClusterServicePanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'title',
            componentType: 'MSClusterService',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'ownernode'},
                {name: 'clusternode'},
                {name: 'coregroup'},
                {name: 'description'},
                {name: 'priority'},
                {name: 'usesMonitorAttribute'},
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
                id: 'title',
                dataIndex: 'title',
                header: _t('Name'),
                sortable: true
            },{
                id: 'clusternode',
                dataIndex: 'clusternode',
                header: _t('Owner Node'),
                renderer: function(clusternode, metadata, record) {
                    return Zenoss.render.Device(clusternode, record.data.ownernode);
                },
                sortable: true,
                width: 200
            },{
                id: 'coregroup',
                dataIndex: 'coregroup',
                header: _t('Core Group'),
                sortable: true,
                width: 180
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
        ZC.MSClusterServicePanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('MSClusterServicePanel', ZC.MSClusterServicePanel);

ZC.registerName('MSClusterResource', _t('Cluster Resource'), _t('Cluster Resources'));

ZC.MSClusterResourcePanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'title',
            componentType: 'MSClusterResource',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'ownernode'},
                {name: 'ownergroup'},
                {name: 'description'},
                {name: 'servicegroup'},
                {name: 'state'},
                {name: 'clusternode'},
                {name: 'usesMonitorAttribute'},
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
                id: 'title',
                dataIndex: 'title',
                header: _t('Name'),
                sortable: true
            },{
                id: 'clusternode',
                dataIndex: 'clusternode',
                header: _t('Owner Node'),
                renderer: function(clusternode, metadata, record) {
                    return Zenoss.render.Device(clusternode, record.data.ownernode);
                },
                sortable: true,
                width: 200
            },{
                id: 'servicegroup',
                dataIndex: 'servicegroup',
                header: _t('Service'),
                renderer: Zenoss.render.win_entityLinkFromGrid,
                sortable: true,
                width: 180
            },{
                id: 'state',
                dataIndex: 'state',
                header: _t('State'),
                sortable: true,
                width: 100
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
        ZC.MSClusterResourcePanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('MSClusterResourcePanel', ZC.MSClusterResourcePanel);

Zenoss.nav.appendTo('Component', [{
    id: 'component_winsqljob',
    text: _t('Jobs'),
    xtype: 'WinSQLJobPanel',
    subComponentGridPanel: true,
    filterNav: function(navpanel) {
        if (navpanel.refOwner.componentType == 'WinDBInstance') {
            return true;
        } else {
            return false;
        }
    },
    setContext: function(uid) {
        ZC.WinSQLJobPanel.superclass.setContext.apply(this, [uid]);
    }
}]);

Zenoss.nav.appendTo('Component', [{
    id: 'component_winbackupdevice',
    text: _t('Backup Devices'),
    xtype: 'WinBackupDevicePanel',
    subComponentGridPanel: true,
    filterNav: function(navpanel) {
        if (navpanel.refOwner.componentType == 'WinDBInstance') {
            return true;
        } else {
            return false;
        }
    },
    setContext: function(uid) {
        ZC.WinBackupDevicePanel.superclass.setContext.apply(this, [uid]);
    }
}]);

Zenoss.nav.appendTo('Component', [{
    id: 'component_msclusterresource',
    text: _t('Resources'),
    xtype: 'MSClusterResourcePanel',
    subComponentGridPanel: true,
    filterNav: function(navpanel) {
        if (navpanel.refOwner.componentType == 'MSMSClusterService') {
            return true;
        } else {
            return false;
        }
    },
    setContext: function(uid) {
        ZC.ClusterResourcePanel.superclass.setContext.apply(this, [uid]);
    }
}]);

Zenoss.nav.appendTo('Component', [{
    id: 'component_windatabase',
    text: _t('Databases'),
    xtype: 'WinDatabasePanel',
    subComponentGridPanel: true,
    filterNav: function(navpanel) {
        if (navpanel.refOwner.componentType == 'WinDBInstance') {
            return true;
        } else {
            return false;
        }
    },
    setContext: function(uid) {
        ZC.WinDatabasePanel.superclass.setContext.apply(this, [uid]);
    }
}]);
})();