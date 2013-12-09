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

function render_na_for_null(value) {
    if (value === null) {
        return 'n/a';
    }

    return value;
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


ZC.WindowsCPUPanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'name',
            componentType: 'WindowsCPU',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'meta_type'},
                {name: 'name'},
                {name: 'title'},
                {name: 'product'},
                {name: 'socket'},
                {name: 'cores'},
                {name: 'threads'},
                {name: 'clockspeed'},
                {name: 'extspeed'},
                {name: 'cacheSizeL1'},
                {name: 'cacheSizeL2'},
                {name: 'cacheSpeedL2'},
                {name: 'cacheSizeL3'},
                {name: 'cacheSpeedL3'},
                {name: 'voltage'},
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
                width: 50
            },{
                id: 'name',
                dataIndex: 'name',
                header: _t('Name'),
            },{
                id: 'socket',
                dataIndex: 'socket',
                header: _t('Socket'),
                width: 60
            },{
                id: 'cores_and_threads',
                dataIndex: 'cores', // also requires threads
                header: _t('Cores'),
                renderer: function(value, metaData, record) {
                    if (value === null) {
                        return 'n/a';
                    }

                    return '<span title="Cores (Logical Processors)">' +
                        record.data.cores +
                        ' (' + record.data.threads + ')' +
                        '</span>';
                },
                width: 55
            },{
                id: 'clockspeed',
                dataIndex: 'clockspeed',
                header: _t('Clock Speed'),
                renderer: function(value) {
                    if (value === null) {
                        return 'n/a';
                    }
                    
                    return value + ' MHz';
                },
                width: 90
            },{
                id: 'l1_cache',
                dataIndex: 'cacheSizeL1',
                header: _t('L1 Cache'),
                renderer: function(value) {
                    if (value === null) {
                        return 'n/a';
                    }

                    return value + ' KB';
                },
                width: 70
            },{
                id: 'l2_cache',
                dataIndex: 'cacheSizeL2', // also requires cacheSpeedL2
                header: _t('L2 Cache'),
                renderer: function (value, metaData, record) {
                    if (value === null) {
                        return 'n/a';
                    }
                    
                    return '<span title="Size @ Speed">' +
                        record.data.cacheSizeL2 + ' KB @ ' +
                        record.data.cacheSpeedL2 + ' MHz' +
                        '</span>';
                },
                width: 115
            },{
                id: 'l3_cache',
                dataIndex: 'cacheSizeL3', // also requires cacheSpeedL3
                header: _t('L3 Cache'),
                renderer: function (value, metaData, record) {
                    if (value === null) {
                        return 'n/a';
                    }
                    
                    return '<span title="Size @ Speed">' +
                        record.data.cacheSizeL3 + ' KB @ ' +
                        record.data.cacheSpeedL3 + ' MHz' +
                        '</span>';
                },
                width: 115
            },{
                id: 'monitored',
                dataIndex: 'monitored',
                header: _t('Monitored'),
                renderer: Zenoss.render.checkbox,
                width: 65
            },{
                id: 'locking',
                dataIndex: 'locking',
                header: _t('Locking'),
                renderer: Zenoss.render.locking_icons,
                width: 65
            }]
        });
        ZC.WindowsCPUPanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('WindowsCPUPanel', ZC.WindowsCPUPanel);


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
                id: 'account',
                dataIndex: 'account',
                header: _t('Start Name'),
                widht: 110,
                sortable: true
            },{
                id: 'startmode',
                dataIndex: 'startmode',
                header: _t('Start Mode'),
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
                {name: 'state'},
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
                    if (clusternode !== null){
                        return Zenoss.render.Device(clusternode, record.data.ownernode);
                    } else {
                        return record.data.ownernode;
                    }
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
        ZC.MSClusterServicePanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('MSClusterServicePanel', ZC.MSClusterServicePanel);


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
                    if (clusternode !== null){
                        return Zenoss.render.Device(clusternode, record.data.ownernode);
                    } else {
                        return record.data.ownernode;
                    }
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


ZC.WinTeamInterfacePanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'description',
            componentType: 'WinTeamInterface',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'name'},
                {name: 'description'},
                {name: 'ipAddressObjs'},
                {name: 'network'},//, mapping:'network.uid'},
                {name: 'macaddress'},
                {name: 'usesMonitorAttribute'},
                {name: 'operStatus'},
                {name: 'adminStatus'},
                {name: 'nic_count'},
                {name: 'status'},
                {name: 'monitor'},
                {name: 'monitored'},
                {name: 'locking'},
                {name: 'duplex'},
                {name: 'netmask'}
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
                dataIndex: 'name',
                header: _t('IP Interface'),
                width: 150
            },{
                id: 'ipAddresses',
                dataIndex: 'ipAddressObjs',
                header: _t('IP Addresses'),
                renderer: function(ipaddresses) {
                    var returnString = '';
                    Ext.each(ipaddresses, function(ipaddress, index) {
                        if (index > 0) returnString += ', ';
                        if (ipaddress && Ext.isObject(ipaddress) && ipaddress.netmask) {
                            var name = ipaddress.name + '/' + ipaddress.netmask;
                            returnString += Zenoss.render.link(ipaddress.uid, undefined, name);
                        }
                        else if (Ext.isString(ipaddress)) {
                            returnString += ipaddress;
                        }
                    });
                    return returnString;
                }
            },{
                id: 'description',
                dataIndex: 'description',
                header: _t('Description')
            },{
                id: 'niccount',
                dataIndex: 'nic_count',
                header: _t('# of NICs'),
                width: 100
            },{
                id: 'macaddress',
                dataIndex: 'macaddress',
                header: _t('MAC Address'),
                sortable: true,
                width: 120
            },{
                id: 'status',
                dataIndex: 'status',
                header: _t('Monitored'),
                renderer: Zenoss.render.pingStatus,
                width: 80
            },{
                id: 'operStatus',
                dataIndex: 'operStatus',
                header: _t('Operational Status'),
                width: 110
            },{
                id: 'adminStatus',
                dataIndex: 'adminStatus',
                header: _t('Admin Status'),
                width: 80
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
        ZC.WinTeamInterfacePanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('WinTeamInterfacePanel', ZC.WinTeamInterfacePanel);


ZC.WindowsInterfacePanel = Ext.extend(ZC.WINComponentGridPanel, {
    subComponentGridPanel: false,

    constructor: function(config) {
        config = Ext.applyIf(config||{}, {
            autoExpandColumn: 'description',
            componentType: 'WindowsInterface',
            fields: [
                {name: 'uid'},
                {name: 'severity'},
                {name: 'name'},
                {name: 'description'},
                {name: 'ipAddressObjs'},
                {name: 'network'},//, mapping:'network.uid'},
                {name: 'macaddress'},
                {name: 'usesMonitorAttribute'},
                {name: 'operStatus'},
                {name: 'adminStatus'},
                {name: 'status'},
                {name: 'monitor'},
                {name: 'monitored'},
                {name: 'locking'},
                {name: 'duplex'},
                {name: 'netmask'}
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
                dataIndex: 'name',
                header: _t('IP Interface'),
                width: 150
            },{
                id: 'ipAddresses',
                dataIndex: 'ipAddressObjs',
                header: _t('IP Addresses'),
                renderer: function(ipaddresses) {
                    var returnString = '';
                    Ext.each(ipaddresses, function(ipaddress, index) {
                        if (index > 0) returnString += ', ';
                        if (ipaddress && Ext.isObject(ipaddress) && ipaddress.netmask) {
                            var name = ipaddress.name + '/' + ipaddress.netmask;
                            returnString += Zenoss.render.link(ipaddress.uid, undefined, name);
                        }
                        else if (Ext.isString(ipaddress)) {
                            returnString += ipaddress;
                        }
                    });
                    return returnString;
                }
            },{
                id: 'description',
                dataIndex: 'description',
                header: _t('Description')
            },{
                id: 'macaddress',
                dataIndex: 'macaddress',
                header: _t('MAC Address'),
                sortable: true,
                width: 120
            },{
                id: 'status',
                dataIndex: 'status',
                header: _t('Monitored'),
                renderer: Zenoss.render.pingStatus,
                width: 80
            },{
                id: 'operStatus',
                dataIndex: 'operStatus',
                header: _t('Operational Status'),
                width: 110
            },{
                id: 'adminStatus',
                dataIndex: 'adminStatus',
                header: _t('Admin Status'),
                width: 80
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
        ZC.WindowsInterfacePanel.superclass.constructor.call(this, config);
    }
});

Ext.reg('WindowsInterfacePanel', ZC.WindowsInterfacePanel);


Zenoss.nav.appendTo('Component', [{
    id: 'component_teaminterface',
    text: _t('Interfaces'),
    xtype: 'WindowsInterfacePanel',
    subComponentGridPanel: true,
    filterNav: function(navpanel) {
        if (navpanel.refOwner.componentType == 'WinTeamInterface') {
            return true;
        } else {
            return false;
        }
    },
    setContext: function(uid) {
        ZC.WindowsInterfacePanel.superclass.setContext.apply(this, [uid]);
    }
}]);

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
        if (navpanel.refOwner.componentType == 'MSClusterService') {
            return true;
        } else {
            return false;
        }
    },
    setContext: function(uid) {
        ZC.MSClusterResourcePanel.superclass.setContext.apply(this, [uid]);
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
