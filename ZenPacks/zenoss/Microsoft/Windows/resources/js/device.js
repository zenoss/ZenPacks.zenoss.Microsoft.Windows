/*##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################*/


(function(){

    Ext.onReady(function() {
        // Hide Software component for wondows cluster
        if(Zenoss.env.PARENT_CONTEXT == "/zport/dmd/Devices/Server/Microsoft/Cluster/devices"){
            var DEVICE_ELEMENTS = "subselecttreepaneldeviceDetailNav";
            Ext.ComponentMgr.onAvailable(DEVICE_ELEMENTS, function(){
                var DEVICE_PANEL = Ext.getCmp(DEVICE_ELEMENTS);
                DEVICE_PANEL.on('afterrender', function() {
                    var tree = Ext.getCmp(DEVICE_PANEL.items.items[0].id);
                    var items = tree.store.data.items;
                    for (i in items){
                        console.log('Item:', items[i].data.id);
                        if (items[i].data.id.match(/software*/)){
                            try {
                                tree.store.remove(items[i]);
                                tree.store.sync();
                            } catch(err){}
                        }
                    }
                });
            });
        }
    });

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
            return '<a href="'+obj.uid+'" onClick="Ext.getCmp(\'component_card\').componentgrid.jumpToEntity(\''+obj.uid +'\', \''+obj.meta_type+'\');return false;">'+obj.title+'</a>';            
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

})();
