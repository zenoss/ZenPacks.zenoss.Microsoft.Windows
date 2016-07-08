##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
import functools
import importlib

from Products.ZenRelations.RelationshipBase import RelationshipBase
from Products.ZenRelations.ToManyContRelationship import ToManyContRelationship

LOG = logging.getLogger('zen.exchange')


def require_zenpack(zenpack_name, default=None):
    '''
    Decorator with mandatory zenpack_name argument.

    If zenpack_name can't be imported, the decorated function or method
    will return default. Otherwise it will execute and return as
    written.

    Usage looks like the following:

        @require_zenpack('ZenPacks.zenoss.Impact')
        def dothatthingyoudo(args):
            return "OK"

        @require_zenpack('ZenPacks.zenoss.Impact', [])
        def returnalistofthings(args):
            return [1, 2, 3]
    '''
    def wrap(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            try:
                importlib.import_module(zenpack_name)
            except ImportError:
                return

            return f(*args, **kwargs)

        return wrapper

    return wrap


# When a manually-created python object is first added to its container, we
# need to reload it, as its in-memory representation is changed.
def addContained(object, relname, target):
    #    print "addContained(" + str(object) + "." + relname + " => " + str(target) + ")"
    rel = getattr(object, relname)

    # contained via a relationship
    if isinstance(rel, ToManyContRelationship):
        rel._setObject(target.id, target)
        return rel._getOb(target.id)

    elif isinstance(rel, RelationshipBase):
        rel.addRelation(target)
        return rel._getOb(target.id)

    # contained via a property
    else:
        # note: in this scenario, you must have the target object's ID the same
        #       as the relationship from the parent object.

        assert(relname == target.id)
        object._setObject(target.id, target)
        return getattr(object, relname)


def addNonContained(object, relname, target):
    rel = getattr(object, relname)
    rel.addRelation(target)
    return target


def create_device(dmd, device_name):
    '''
    Return a Windows Device suitable for Impact functional testing.
    '''
    # DeviceClass
    dc = dmd.Devices.getOrganizer('/Server/Microsoft/Windows')

    # Endpoint
    windows1 = dc.createInstance(device_name)

    windows1.domain_controller = True
    windows1.manageIp = '10.10.10.10'
    windows1.msexchangeversion = 'MSExchangeIS'
    windows1.clusterdevices = ['cluster1']

    from ZenPacks.zenoss.Microsoft.Windows.Interface import Interface
    from ZenPacks.zenoss.Microsoft.Windows.CPU import CPU
    from ZenPacks.zenoss.Microsoft.Windows.FileSystem import FileSystem
    from ZenPacks.zenoss.Microsoft.Windows.OSProcess import OSProcess
    from ZenPacks.zenoss.Microsoft.Windows.WinIIS import WinIIS
    from ZenPacks.zenoss.Microsoft.Windows.WinService import WinService
    from ZenPacks.zenoss.Microsoft.Windows.WinSQLBackup import WinSQLBackup
    from ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase import WinSQLDatabase
    from ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance import WinSQLInstance
    from ZenPacks.zenoss.Microsoft.Windows.WinSQLJob import WinSQLJob
    from Products.ZenModel.Software import Software
    from Products.ZenModel.IpRouteEntry import IpRouteEntry

    int1 = addContained(windows1.os, 'interfaces', Interface('int1'))
    int1.perfmonInstance = '/network adapter(int1)/'

    cpu1 = addContained(windows1.hw, 'cpus', CPU('cpu1'))
    cpu1.perfmonInstance = '/Processor(cpu1)/'

    fs1 = addContained(windows1.os, 'filesystems', FileSystem('fs1'))
    fs1.perfmonInstance = '/filesystem(fs1)/'

    addContained(windows1.os, 'processes', OSProcess('pr1'))

    addContained(windows1.os, 'winrmiis', WinIIS('iis1'))

    addContained(windows1.os, 'winservices', WinService('ws1'))

    instance1 = addContained(windows1.os, 'winsqlinstances', WinSQLInstance('instance1'))
    addContained(instance1, 'backups', WinSQLBackup('backup1'))
    addContained(instance1, 'databases', WinSQLDatabase('db1'))
    addContained(instance1, 'jobs', WinSQLJob('job1'))
    addContained(windows1.os, 'software', Software('soft1'))
    addContained(windows1.os, 'routes', IpRouteEntry('route1'))

    return windows1


def create_cluster_device(dmd, device_name):
    '''
    Return a Windows Cluster Device suitable for analytics bundle create script.
    '''
    # DeviceClass
    dc = dmd.Devices.getOrganizer('/Server/Microsoft/Cluster')

    # Endpoint
    cluster1 = dc.createInstance(device_name)
    cluster1.domain_controller = True
    cluster1.manageIp = '10.10.10.10'
    cluster1.msexchangeversion = 'MSExchangeIS'
    cluster1.clusterdevices = ['node1']

    from ZenPacks.zenoss.Microsoft.Windows.ClusterDisk import ClusterDisk
    from ZenPacks.zenoss.Microsoft.Windows.ClusterInterface import ClusterInterface
    from ZenPacks.zenoss.Microsoft.Windows.ClusterNetwork import ClusterNetwork
    from ZenPacks.zenoss.Microsoft.Windows.ClusterNode import ClusterNode
    from ZenPacks.zenoss.Microsoft.Windows.ClusterResource import ClusterResource
    from ZenPacks.zenoss.Microsoft.Windows.ClusterService import ClusterService

    node1 = addContained(cluster1.os, 'clusternodes', ClusterNode('node1'))

    addContained(node1.os, 'clusterdisks', ClusterDisk('disk1'))
    addContained(node1.os, 'clusterinterfaces', ClusterInterface('interface1'))

    service1 = addContained(cluster1.os, 'clusterservices', ClusterService('service1'))
    addContained(service1, 'clusterresources', ClusterResource('resource1'))

    addContained(cluster1.os, 'clusternetworks', ClusterNetwork('network1'))

    return cluster1
