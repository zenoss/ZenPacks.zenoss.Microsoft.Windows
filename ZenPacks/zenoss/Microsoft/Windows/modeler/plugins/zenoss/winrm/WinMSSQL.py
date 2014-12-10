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
import json

from twisted.internet import defer

from Products.DataCollector.plugins.DataMaps \
    import ObjectMap, RelationshipMap

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath, \
    getSQLAssembly, filter_sql_stdout, prepare_zDBInstances

addLocalLibPath()

from txwinrm.shell import create_single_shot_command


class SQLCommander(object):
    '''
    Custom WinRS client to construct and run PowerShell commands.
    '''

    def __init__(self, conn_info):
        self.winrs = create_single_shot_command(conn_info)

    PS_COMMAND = "powershell -NoLogo -NonInteractive -NoProfile " \
        "-OutputFormat TEXT -Command "

    LOCAL_INSTANCES_PS_SCRIPT = '''
        <# Get registry key for instances (with 2003 or 32/64 Bit 2008 base key) #>
        $reg = [Microsoft.Win32.RegistryKey]::OpenRemoteBaseKey('LocalMachine', $hostname);
        $baseKeys = 'SOFTWARE\Microsoft\Microsoft SQL Server',
            'SOFTWARE\Wow6432Node\Microsoft\Microsoft SQL Server';
        foreach ($regPath in $baseKeys) {
            $regKey= $reg.OpenSubKey($regPath);
            If ($regKey -eq $null) {Continue};

            <# Get installed instances' names (both cluster and local) #>
            If ($regKey.GetSubKeyNames() -contains 'Instance Names') {
                $regKey = $reg.OpenSubKey($regpath+'\Instance Names\SQL');
                $instances = @($regkey.GetValueNames());
            } ElseIf ($regKey.GetValueNames() -contains 'InstalledInstances') {
                $instances = $regKey.GetValue('InstalledInstances');
            } Else {Continue};

            <# Get only local instances' names #>
            $local_instances = New-Object System.Collections.Arraylist;
            $instances | % {
                $instanceValue = $regKey.GetValue($_);
                $instanceReg = $reg.OpenSubKey($regpath+'\\'+$instanceValue);
                If ($instanceReg.GetSubKeyNames() -notcontains 'Cluster') {
                    $local_instances += $_;
                };
            };
            break;
        };
        $local_instances | % {write-host \"instances:\"$_};
    '''

    CLUSTER_INSTANCES_PS_SCRIPT = '''
        $domain = (gwmi WIN32_ComputerSystem).Domain;
        Import-Module FailoverClusters;
        $cluster_instances = Get-ClusterResource
            | ? {$_.ResourceType -like 'SQL Server'}
            | % {$ownernode = $_.OwnerNode; $_
            | Get-ClusterParameter -Name VirtualServerName,InstanceName
            | Group ClusterObject | Select
            @{Name='SQLInstance';Expression={($_.Group | select -expandproperty Value) -join '\\'}},
            @{Name='OwnerNode';Expression={($ownernode, $domain) -join '.'}}};
        $cluster_instances | % {write-host \"instances:\"($_).OwnerNode\($_).SQLInstance};
    '''

    HOSTNAME_PS_SCRIPT = '''
        $hostname = hostname; write-host \"hostname:\"$hostname;
    '''

    def get_instances_names(self, is_cluster):
        '''
        Run script to retrieve DB instances' names and hostname either
        available in the cluster or installed on the local machine,
        according to the 'is_cluster' parameter supplied.
        '''
        psinstance_script = self.CLUSTER_INSTANCES_PS_SCRIPT if is_cluster \
            else self.LOCAL_INSTANCES_PS_SCRIPT
        return self.run_command(
            psinstance_script.replace('\n', ' ') + self.HOSTNAME_PS_SCRIPT
        )

    def run_command(self, pscommand):
        '''
        Run PowerShell command.
        '''
        buffer_size = ('$Host.UI.RawUI.BufferSize = New-Object '
                       'Management.Automation.Host.Size (4096, 25);')
        command = "{0} \"{1} & {{{2}}}\"".format(
            self.PS_COMMAND, buffer_size, pscommand)
        return self.winrs.run_command(command)


class WinMSSQL(WinRMPlugin):

    deviceProperties = WinRMPlugin.deviceProperties + (
        'zDBInstances',
        'getDeviceClassName'
        )

    @defer.inlineCallbacks
    def collect(self, device, log):
        # Check if the device is a cluster device.
        isCluster = True if 'Microsoft/Cluster' in device.getDeviceClassName \
            else False

        dbinstance = prepare_zDBInstances(device.zDBInstances)
        username = device.windows_user
        password = device.windows_password
        login_as_user = False
        dblogins = {}
        eventmessage = 'Error parsing zDBInstances'

        try:
            dbinstance = json.loads(dbinstance)
            users = [el.get('user') for el in filter(None, dbinstance)]
            if ''.join(users):
                for el in filter(None, dbinstance):
                    dblogins[el.get('instance')] = dict(
                        username=el.get('user'),
                        password=el.get('passwd')
                    )
            else:
                login_as_user = True
                for el in filter(None, dbinstance):
                    dblogins[el.get('instance')] = dict(
                        username=username,
                        password=password
                    )
            results = {'clear': eventmessage}
        except (ValueError, TypeError, IndexError):
            # Error with dbinstance names or password
            results = {'error': eventmessage}
            defer.returnValue(results)

        conn_info = self.conn_info(device)
        winrs = SQLCommander(conn_info)

        dbinstances = winrs.get_instances_names(isCluster)
        instances = yield dbinstances

        maps = {}
        instance_oms = []
        database_oms = []
        backup_oms = []
        jobs_oms = []
        server_config = {}
        sqlhostname = ''

        for serverconfig in instances.stdout:
            key, value = serverconfig.split(':', 1)
            serverlist = []
            if key in server_config:
                serverlist = server_config[key]
                serverlist.append(value.strip())
                server_config[key] = serverlist
            else:
                serverlist.append(value.strip())
                server_config[key] = serverlist

        if not server_config.get('instances'):
            eventmessage = 'No MSSQL Servers are installed but modeler is enabled'
            results = {'error': eventmessage}
            defer.returnValue(results)

        sqlhostname = server_config['hostname'][0]
        # Set value for device sqlhostname property
        device_om = ObjectMap()
        device_om.sqlhostname = sqlhostname
        for instance in server_config['instances']:
            owner_node = ''  # Leave empty for local databases.
            # For cluster device, create a new a connection to each node,
            # which owns network instances.
            if isCluster:
                try:
                    owner_node, sql_server, instance = instance.split('\\') 
                    device.windows_servername = owner_node.strip()
                    conn_info = self.conn_info(device)
                    winrs = SQLCommander(conn_info)
                except ValueError:
                    log.error('Owner node for DB Instance {0} was not found'.format(
                        instance))
                    continue

            if instance not in dblogins:
                log.info("DB Instance {0} found but was not set in zDBInstances".format(
                    instance))
                continue

            om_instance = ObjectMap()
            om_instance.id = self.prepId(instance)
            om_instance.title = instance
            om_instance.instancename = instance
            instance_oms.append(om_instance)
            if instance in dblogins:
                sqlConnection = []

                if instance == 'MSSQLSERVER':
                    sqlserver = sqlhostname
                else:
                    sqlserver = '{0}\{1}'.format(sqlhostname, instance)

                if isCluster:
                    sqlserver = sql_server.strip()

                sqlusername = dblogins[instance]['username']
                sqlpassword = dblogins[instance]['password']

                # DB Connection Object
                sqlConnection.append("$con = new-object " \
                    "('Microsoft.SqlServer.Management.Common.ServerConnection')" \
                    "'{0}', '{1}', '{2}';".format(sqlserver, sqlusername, sqlpassword))

                if login_as_user:
                    log.debug("Windows auth %s / %s" % (sqlusername, sqlpassword))
                    # Login using windows credentials
                    sqlConnection.append("$con.LoginSecure=$true;")
                    sqlConnection.append("$con.ConnectAsUser=$true;")
                    # Omit domain part of username
                    sqlConnection.append("$con.ConnectAsUserName='{0}';".format(sqlusername.split("\\")[-1]))
                    sqlConnection.append("$con.ConnectAsUserPassword='{0}';".format(sqlpassword))
                else:
                    log.debug("DB auth %s / %s" % (sqlusername, sqlpassword))
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

                databases = yield winrs.run_command(
                    ''.join(getSQLAssembly() + sqlConnection + db_sqlConnection)
                )
                check_username(databases, instance, log)
                for dbobj in filter_sql_stdout(databases.stdout):
                    db = dbobj.split('\t')
                    dbdict = {}

                    for dbitem in db:
                        try:
                            key, value = dbitem.split('---')
                            dbdict[key.lower()] = value.strip()
                        except (ValueError):
                            log.info('Error parsing returned values : {0}'.format(
                                dbitem))

                    lastlogbackupdate = None
                    if ('lastlogbackupdate' in dbdict) \
                    and (dbdict['lastlogbackupdate'][:8] != '1/1/0001'):
                        lastlogbackupdate = dbdict['lastlogbackupdate']

                    lastbackupdate = None
                    if ('lastbackupdate' in dbdict) \
                    and (dbdict['lastbackupdate'][:8] != '1/1/0001'):
                        lastbackupdate = dbdict['lastbackupdate']

                    if ('id' in dbdict):
                        om_database = ObjectMap()
                        om_database.id = self.prepId(instance + dbdict['id'])
                        om_database.title = dbdict['name'][1:-1]
                        om_database.instancename = om_instance.id
                        om_database.version = dbdict['version']
                        om_database.owner = dbdict['owner']
                        om_database.lastbackupdate = lastbackupdate
                        om_database.lastlogbackupdate = lastlogbackupdate
                        om_database.isaccessible = dbdict['isaccessible']
                        om_database.collation = dbdict['collation']
                        om_database.createdate = str(dbdict['createdate'])
                        om_database.defaultfilegroup = dbdict['defaultfilegroup']
                        om_database.primaryfilepath = dbdict['primaryfilepath']
                        om_database.cluster_node_server = '{0}//{1}'.format(
                            owner_node.strip(), sqlserver)

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

                backuplist = winrs.run_command(
                    ''.join(getSQLAssembly() + sqlConnection + backup_sqlConnection)
                )
                backups = yield backuplist
                for backupobj in filter_sql_stdout(backups.stdout):
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
                jobsquery = (
                    "select s.name as jobname, s.job_id as jobid, "
                    "s.enabled as enabled, s.date_created as datecreated, "
                    # Replace each new line with a space in description.
                    "replace(replace(s.description, char(13), char(32)), "
                    "char(10), char(32)) as description, "
                    "l.name as username from msdb..sysjobs s left join "
                    "master.sys.syslogins l on s.owner_sid = l.sid"
                )

                job_sqlConnection = []
                job_sqlConnection.append("$db = $server.Databases[0];")
                job_sqlConnection.append("$ds = $db.ExecuteWithResults('{0}');".format(jobsquery))
                job_sqlConnection.append('$ds.Tables | Format-List;')

                jobslist = winrs.run_command(
                    ''.join(getSQLAssembly() + sqlConnection + job_sqlConnection)
                )
                jobs = yield jobslist
                for job in filter_sql_stdout(jobs.stdout):
                    # Make sure that the job description length does not go 
                    # beyond the buffer size (4096 characters).
                    if ':' not in job:
                        continue

                    key, value = job.split(':', 1)
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
                            om_jobs.enabled = 'Yes'\
                                if value.strip() == '1' else 'No'
                        elif key.strip() == 'description':
                            om_jobs.description = value.strip()
                        elif key.strip() == 'datecreated':
                            om_jobs.datecreated = str(value)
                        elif key.strip() == 'username':
                            om_jobs.username = value.strip()
                            jobs_oms.append(om_jobs)

        maps['clear'] = eventmessage
        maps['databases'] = database_oms
        maps['instances'] = instance_oms
        maps['backups'] = backup_oms
        maps['jobs'] = jobs_oms
        maps['device'] = device_om

        defer.returnValue(maps)

    def process(self, device, results, log):
        log.info('Modeler %s processing data for device %s',
                 self.name(), device.id)
        maps = []
        if results.get('device'):
            maps.append(results['device'])

        eventmessage = results.get('error')
        if eventmessage:
            log.error(eventmessage)
            return

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


def check_username(databases, instance, log):
    stderr = ''.join(databases.stderr)
    if not databases.stdout and\
        (('Exception calling "Connect" with "0" argument(s): '
            '"Failed to connect to server'
            in stderr) or (
            'The following exception was thrown when trying to enumerate the '
            'collection: "Logon failure: unknown user name or bad password.'
            in stderr) or (
            'The following exception was thrown when trying to enumerate the '
            'collection: "Anattempt was made to logon, but the network logon '
            'service was not started.' in stderr) or (
            'The following exception was thrown when trying to enumerate the '
            'collection: "There are currently no logon servers available to '
            'service the logon request.' in stderr)):
        log.error(
            'Incorrect username/password for the {0} instance.'.format(
                instance
            ))
