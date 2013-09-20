##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Windows MS SQL Server Collection

Collection is done via PowerShell script due to the lack of information
available in WMI.

"""
from twisted.internet import defer

from Products.DataCollector.plugins.DataMaps \
    import ObjectMap, RelationshipMap
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from Products.ZenUtils.Utils import prepId
from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath

addLocalLibPath()

from txwinrm.util import ConnectionInfo
from txwinrm.shell import create_single_shot_command


class WinMSSQL(PythonPlugin):

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        'zWinRMPort',
        'zDBInstanceLogin',
        'zDBInstancePassword',
        )

    @defer.inlineCallbacks
    def collect(self, device, log):
        hostname = device.manageIp

        username = device.zWinUser
        auth_type = 'kerberos' if '@' in username else 'basic'
        password = device.zWinPassword

        # Sample data for zDBInstanceLogin
        # MSSQLSERVER;ZenossInstance2

        # Sample data for zDBInstancePassword
        # sa:Sup3rPa$$;sa:WRAAgf4234@#$

        dbinstance = device.zDBInstanceLogin
        dbinstancepassword = device.zDBInstancePassword

        dblogins = {}

        if len(dbinstance) > 0 and len(dbinstancepassword) > 0:
            arrInstance = dbinstance.split(';')
            arrPassword = dbinstancepassword.split(';')
            i = 0
            for instance in arrInstance:
                dbuser, dbpass = arrPassword[i].split(':')
                i = i + 1
                dblogins[instance] = {'username': dbuser, 'password': dbpass}
        else:
            dblogins['MSSQLSERVER'] = {'username': 'sa', 'password': password}

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

        #sqlserver = 'SQL1\ZENOSSINSTANCE2'
        #sqlusername = 'sa'
        #sqlpassword = 'Z3n0ss12345'

        # Base command line setup for powershell
        pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

        psInstances = []

        # Get registry key for instances
        psInstances.append("$instances = get-itemproperty \'HKLM:\Software\Wow6432Node\Microsoft\Microsoft SQL Server\';")
        psInstances.append("$instances.InstalledInstances;")

        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(psInstances))

        dbinstances = winrs.run_command(command)
        instances = yield dbinstances
        maps = {}
        instance_oms = []
        database_oms = []
        backup_oms = []
        jobs_oms = []

        for instance in instances.stdout:
            om_instance = ObjectMap()
            om_instance.id = self.prepId(instance)
            om_instance.instancename = instance
            instance_oms.append(om_instance)

            if instance in dblogins:
                sqlConnection = []
                # AssemblyNames required for SQL interactions
                sqlConnection.append("add-type -AssemblyName 'Microsoft.SqlServer.ConnectionInfo';")
                sqlConnection.append("add-type -AssemblyName 'Microsoft.SqlServer.Smo';")

                if instance == 'MSSQLSERVER':
                    sqlserver = 'SQL1'
                else:
                    sqlserver = 'SQL1\{1}'.format(device.manageIp, instance)
                sqlusername = dblogins[instance]['username']
                sqlpassword = dblogins[instance]['password']

                # DB Connection Object
                sqlConnection.append("$con = new-object " \
                    "('Microsoft.SqlServer.Management.Common.ServerConnection')" \
                    "'{0}', '{1}', '{2}';".format(sqlserver, sqlusername, sqlpassword))

                sqlConnection.append("$con.Connect();")

                # Connect to Database Server
                sqlConnection.append("$server = new-object " \
                    "('Microsoft.SqlServer.Management.Smo.Server') $con;")

                sqlConnection.append('$server.Databases | foreach {' \
                    'write-host \"Name:\" $_.Name,' \
                    '\"-Version:\" $_.Version,' \
                    '\"-IsAccessible:\" $_.IsAccessible,' \
                    '\"-ID:\" $_.ID,' \
                    '\"-Owner:\" $_.Owner,' \
                    '\"-LastBackupDate:\" $_.LastBackupDate, '\
                    '\"-LastLogBackupDate:\" $_.LastLogBackupDate' \
                    '};')

                command = "{0} \"& {{{1}}}\"".format(
                    pscommand,
                    ''.join(sqlConnection))

                instancedatabases = winrs.run_command(command)
                databases = yield instancedatabases

                database_oms.append((databases.stdout))

        maps['databases'] = database_oms
        maps['instances'] = instance_oms
        maps['backups'] = backup_oms
        maps['jobs'] = jobs_oms

        defer.returnValue(maps)

    def process(self, device, results, log):

        import pdb; pdb.set_trace()
        log.info('Modeler %s processing data for device %s',
            self.name(), device.id)

        maps = []
        siteMap = []

        maps.append(RelationshipMap(
            relname="winrsmysql",
            compname="os",
            modname="ZenPacks.zenoss.Microsoft.Windows.WinIIS",
            objmaps=siteMap))

        return maps
