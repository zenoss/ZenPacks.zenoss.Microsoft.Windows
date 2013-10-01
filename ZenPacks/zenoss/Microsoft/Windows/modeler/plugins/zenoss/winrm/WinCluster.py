##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Windows Cluster System Collection

"""
from twisted.internet import defer

from Products.DataCollector.plugins.DataMaps import  ObjectMap, RelationshipMap
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin

from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath

addLocalLibPath()

from txwinrm.util import ConnectionInfo
from txwinrm.shell import create_single_shot_command


class WinCluster(PythonPlugin):

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        'zFileSystemMapIgnoreNames',
        'zFileSystemMapIgnoreTypes',
        'zInterfaceMapIgnoreNames',
        'zWinRMPort',
        )

    @defer.inlineCallbacks
    def collect(self, device, log):

        maps = {}

        hostname = device.manageIp
        username = device.zWinUser
        auth_type = 'kerberos' if '@' in username else 'basic'
        password = device.zWinPassword
        scheme = 'http'
        port = int(device.zWinRMPort)
        connectiontype = 'Keep-Alive'
        keytab = ''

        conn_info = ConnectionInfo(
            hostname,
            auth_type,
            username,
            password,
            scheme,
            port,
            connectiontype,
            keytab)

        winrs = create_single_shot_command(conn_info)

        # Collection for cluster nodes
        pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

        psClusterCommands = []
        psClusterCommands.append("import-module failoverclusters;")

        psClusterHosts = []
        psClusterHosts.append("get-clusternode | foreach {$_.Name};")

        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(psClusterCommands + psClusterHosts))

        clusternodes = winrs.run_command(command)
        clusternode = yield clusternodes

        # Collection for cluster groups
        psResources = []
        clustergroupitems = ('$_.Name', '$_.IsCoreGroup', '$_.OwnerNode', '$_.State',
            '$_.Description', '$_.Id', '$_.Priority')

        psResources.append('get-clustergroup | foreach {{{0}}};'.format(
            " + '|' + ".join(clustergroupitems)
            ))

        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(psClusterCommands + psResources))

        resources = winrs.run_command(command)
        resource = yield resources

        # Collection for cluster applications

        psApplications = []
        clusterappitems = ('$_.Name', '$_.OwnerGroup', '$_.OwnerNode', '$_.State',
            '$_.Description')

        psApplications.append('get-clusterresource | foreach {{{0}}};'.format(
            " + '|' + ".join(clusterappitems)
            ))

        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(psClusterCommands + psApplications))

        clusterapps = winrs.run_command(command)
        clusterapp = yield clusterapps

        maps['apps'] = clusterapp.stdout
        maps['resources'] = resource.stdout
        maps['nodes'] = clusternode.stdout

        defer.returnValue(maps)

    def process(self, device, results, log):
        log.info('Modeler %s processing data for device %s',
                 self.name(), device.id)
        maps = []

        map_resources_oms = []
        ownergroups = {}
        map_apps_to_resource = {}

        nodes = results['nodes']
        cs_om = ObjectMap()
        cs_om.setClusterHostMachine = nodes
        maps.append(cs_om)

        # Cluster Resource Maps

        resources = results['resources']

        for resource in resources:
            resourceline = resource.split("|")
            res_om = ObjectMap()

            res_om.id = self.prepId(resourceline[5])
            res_om.title = resourceline[0]
            res_om.coregroup = resourceline[1]
            res_om.ownernode = resourceline[2]
            res_om.state = resourceline[3]
            res_om.description = resourceline[4]
            res_om.priority = resourceline[6]

            if res_om.title not in ownergroups:
                ownergroups[res_om.title] = res_om.id

            map_resources_oms.append(res_om)
        # Cluster Application and Services

        applications = results['apps']

        for app in applications:
            appline = app.split("|")
            app_om = ObjectMap()
            app_om.id = self.prepId(appline[0])
            app_om.title = appline[0]
            app_om.ownernode = appline[2]
            app_om.description = appline[4]
            app_om.ownergroup = appline[1]
            app_om.state = appline[3]

            groupid = ownergroups[app_om.ownergroup]
            appsom = []
            if groupid in map_apps_to_resource:
                appsom = map_apps_to_resource[groupid]
            appsom.append(app_om)
            map_apps_to_resource[groupid] = appsom

        maps.append(RelationshipMap(
            compname="os",
            relname="clusterservices",
            modname="ZenPacks.zenoss.Microsoft.Windows.ClusterService",
            objmaps=map_resources_oms))

        for resourceid, apps in map_apps_to_resource.items():
            maps.append(RelationshipMap(
                compname="os/clusterservices/" + resourceid,
                relname="clusterresources",
                modname="ZenPacks.zenoss.Microsoft.Windows.ClusterResource",
                objmaps=apps))

        return maps
