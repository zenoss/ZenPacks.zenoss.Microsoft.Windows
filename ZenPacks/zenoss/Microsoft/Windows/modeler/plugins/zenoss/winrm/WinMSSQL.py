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
        'zDBInstances',
        'zDBInstancesPassword',
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

        dbinstance = device.zDBInstances
        dbinstancepassword = device.zDBInstancesPassword

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

        psInstances.append("$hostname=hostname;")

        # Get registry key for instances
        # 32/64 Bit 2008
        psInstances.append("if (get-itemproperty \'HKLM:\Software\Wow6432Node\Microsoft\Microsoft SQL Server\')")
        psInstances.append("{$instances = get-itemproperty \'HKLM:\Software\Wow6432Node\Microsoft\Microsoft SQL Server\';}")

        # 2003
        psInstances.append("if (get-itemproperty \'HKLM:\Software\Microsoft\Microsoft SQL Server\')")
        psInstances.append("{$instances = get-itemproperty \'HKLM:\Software\Microsoft\Microsoft SQL Server\';}")

        psInstances.append("$instances.InstalledInstances | foreach {write-host \"instances:\"$_};")
        psInstances.append("write-host \"hostname:\"$hostname;")

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
        server_config = {}
        sqlhostname = ''

        for serverconfig in instances.stdout:
            key, value = serverconfig.split(':')
            serverlist = []
            if key in server_config:
                serverlist = server_config[key]
                serverlist.append(value.strip())
                server_config[key] = serverlist
            else:
                serverlist.append(value.strip())
                server_config[key] = serverlist

        sqlhostname = server_config['hostname'][0]
        for instance in server_config['instances']:
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
                    sqlserver = sqlhostname
                else:
                    sqlserver = '{0}\{1}'.format(sqlhostname, instance)

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

                db_sqlConnection = []
                # Get database information
                db_sqlConnection.append('$server.Databases | foreach {' \
                    'write-host \"Name---\" $_,' \
                    '\"`tVersion---\" $_.Version,' \
                    '\"`tIsAccessible---\" $_.IsAccessible,' \
                    '\"`tID---\" $_.ID,' \
                    '\"`tOwner---\" $_.Owner,' \
                    '\"`tLastBackupDate---\" $_.LastBackupDate,'\
                    '\"`tCollation---\" $_.Collation,'\
                    '\"`tCreateDate---\" $_.CreateDate,'\
                    '\"`tDefaultFileGroup---\" $_.DefaultFileGroup,'\
                    '\"`tPrimaryFilePath---\" $_.PrimaryFilePath,'\
                    '\"`tLastLogBackupDate---\" $_.LastLogBackupDate' \
                    '};')

                command = "{0} \"& {{{1}}}\"".format(
                    pscommand,
                    ''.join(sqlConnection + db_sqlConnection))

                instancedatabases = winrs.run_command(command)
                databases = yield instancedatabases

                for dbobj in databases.stdout:
                    db = dbobj.split('\t')
                    dbdict = {}

                    for dbitem in db:
                        try:
                            key, value = dbitem.split('---')
                            dbdict[key.lower()] = value.strip()
                        except:
                            log.info('Error parsing returned values : {0}'.format(
                                dbitem))

                    om_database = ObjectMap()
                    om_database.id = self.prepId(instance + dbdict['id'])
                    om_database.title = dbdict['name'][1:-1]
                    om_database.instancename = om_instance.id
                    om_database.version = dbdict['version']
                    om_database.owner = dbdict['owner']
                    om_database.lastbackupdate = dbdict['lastbackupdate']
                    om_database.lastlogbackupdate = dbdict['lastlogbackupdate']
                    om_database.isaccessible = dbdict['isaccessible']
                    om_database.collation = dbdict['collation']
                    om_database.defaultfilegroup = dbdict['defaultfilegroup']
                    #om_database.databaseguid = dbdict['databaseguid']
                    om_database.primaryfilepath = dbdict['primaryfilepath']

                    database_oms.append(om_database)

                # Get SQL Backup Jobs information
                backup_sqlConnection = []
                # Get database information
                backup_sqlConnection.append('$server.BackupDevices | foreach {' \
                    'write-host \"Name---\" $_.Name,' \
                    '\"`tDeviceType---\" $_.BackupDeviceType,' \
                    '\"`tPhysicalLocation---\" $_.PhysicalLocation,' \
                    '\"`tStatus---\" $_.State' \
                    '};')

                command = "{0} \"& {{{1}}}\"".format(
                    pscommand,
                    ''.join(sqlConnection + backup_sqlConnection))

                backuplist = winrs.run_command(command)
                backups = yield backuplist
                for backupobj in backups.stdout:
                    backup = backupobj.split('\t')
                    backupdict = {}

                    for backupitem in backup:
                        key, value = backupitem.split('---')
                        backupdict[key.lower()] = value.strip()

                    om_backup = ObjectMap()
                    om_backup.id = self.prepId(instance + backupdict['name'])
                    om_backup.title = backupdict['name']
                    om_backup.devicetype = backupdict['devicetype']
                    om_backup.physicallocation = backupdict['physicallocation']
                    om_backup.status = backupdict['status']
                    om_backup.instancename = om_instance.id

                    backup_oms.append(om_backup)

                # Get SQL Jobs information
                jobsquery = "select s.name as jobname, s.job_id as jobid, " \
                "s.enabled as enabled, s.description as description, " \
                "l.name as username from " \
                "msdb..sysjobs s left join master.sys.syslogins l on s.owner_sid = l.sid"

                job_sqlConnection = []
                job_sqlConnection.append("$db = $server.Databases[0];")
                job_sqlConnection.append("$ds = $db.ExecuteWithResults('{0}');".format(jobsquery))
                job_sqlConnection.append('$ds.Tables | Format-List;')

                command = "{0} \"& {{{1}}}\"".format(
                    pscommand,
                    ''.join(sqlConnection + job_sqlConnection))

                jobslist = winrs.run_command(command)
                jobs = yield jobslist
                for job in jobs.stdout:
                    key, value = job.split(':')
                    if key.strip() == 'jobname':
                        #New Job Record
                        om_jobs = ObjectMap()
                        om_jobs.instancename = om_instance.id
                        om_jobs.title = value.strip()
                    else:
                        if key.strip() == 'jobid':
                            om_jobs.jobid = value.strip()
                            om_jobs.id = self.prepId(om_jobs.jobid)
                        elif key.strip() == 'enabled':
                            om_jobs.enabled = value.strip()
                        elif key.strip() == 'description':
                            om_jobs.description = value.strip()
                        elif key.strip() == 'datecreated':
                            om_jobs.datecreated = value.strip()
                        elif key.strip() == 'username':
                            om_jobs.username = value.strip()
                            jobs_oms.append(om_jobs)

        maps['databases'] = database_oms
        maps['instances'] = instance_oms
        maps['backups'] = backup_oms
        maps['jobs'] = jobs_oms

        defer.returnValue(maps)

    def process(self, device, results, log):
        log.info('Modeler %s processing data for device %s',
            self.name(), device.id)

        map_dbs_instance_oms = {}
        map_jobs_instance_oms = {}
        map_backups_instance_oms = {}

        # Build instance object maps

        for database in results['databases']:
            instance = database.instancename
            databaseom = []
            if instance in map_dbs_instance_oms:
                databaseom = map_dbs_instance_oms[instance]

            databaseom.append(database)
            map_dbs_instance_oms[instance] = databaseom

        for job in results['jobs']:
            instance = job.instancename
            jobom = []
            if instance in map_jobs_instance_oms:
                jobom = map_jobs_instance_oms[instance]

            jobom.append(job)
            map_jobs_instance_oms[instance] = jobom

        for backup in results['backups']:
            instance = backup.instancename
            backupom = []
            if instance in map_backups_instance_oms:
                backupom = map_backups_instance_oms[instance]

            backupom.append(backup)
            map_backups_instance_oms[instance] = backupom

        maps = []

        maps.append(RelationshipMap(
            relname="winsqlinstances",
            compname="os",
            modname="ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance",
            objmaps=results['instances']))

        for instance, backups in map_backups_instance_oms.items():
            maps.append(RelationshipMap(
                relname="backups",
                compname="os/winsqlinstances/" + instance,
                modname="ZenPacks.zenoss.Microsoft.Windows.WinSQLBackup",
                objmaps=backups))

        for instance, jobs in map_jobs_instance_oms.items():
            maps.append(RelationshipMap(
                relname="jobs",
                compname="os/winsqlinstances/" + instance,
                modname="ZenPacks.zenoss.Microsoft.Windows.WinSQLJob",
                objmaps=jobs))

        for instance, dbs in map_dbs_instance_oms.items():
            maps.append(RelationshipMap(
                relname="databases",
                compname="os/winsqlinstances/" + instance,
                modname="ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase",
                objmaps=dbs))

        return maps
