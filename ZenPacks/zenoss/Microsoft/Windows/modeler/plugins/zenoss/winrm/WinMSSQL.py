##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012-2017, all rights reserved.
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

from collections import defaultdict

from twisted.internet import defer

from Products.DataCollector.plugins.DataMaps \
    import ObjectMap, RelationshipMap

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath, \
    getSQLAssembly, filter_sql_stdout, prepare_zDBInstances, get_ao_sql_instance_id
from ZenPacks.zenoss.Microsoft.Windows.utils import save, SqlConnection, use_sql_always_on, \
    parse_winrs_response, get_sql_instance_naming_info, recursive_mapping_update, \
    get_console_output_from_parts, lookup_ag_quorum_state, fill_ag_om, fill_ar_om, fill_al_om, fill_adb_om, \
    get_sql_instance_original_name

from txwinrm.WinRMClient import SingleCommandClient

addLocalLibPath()


class SQLCommander(object):
    '''
    Custom WinRS client to construct and run PowerShell commands.
    '''

    def __init__(self, conn_info, log):
        self.winrs = SingleCommandClient(conn_info)
        self.log = log

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
                    $version = $instanceReg.OpenSubKey('MSSQLServer\CurrentVersion').GetValue('CurrentVersion');
                    $instance_ver = $_;$instance_ver+=':';$instance_ver+=$version;
                    $local_instances += $_+':'+$version;
                };
            };
            break;
        };
        $local_instances | % {write-host \"instances:\"$_};
    '''

    CLUSTER_INSTANCES_PS_SCRIPT = '''
        $use_cim = $PSVersionTable.PSVersion.Major -gt 2;
        if ($use_cim) {
            $domain = (get-ciminstance WIN32_ComputerSystem).Domain;
        }
        else {
            $domain = (gwmi WIN32_ComputerSystem).Domain;
        }
        Import-Module FailoverClusters;
        $cluster_instances = Get-ClusterResource
            | ? {$_.ResourceType -like 'SQL Server'}
            | % {$ownernode = $_.OwnerNode; $_
            | Get-ClusterParameter -Name VirtualServerName,InstanceName
            | Group ClusterObject | Select
            @{Name='SQLInstance';Expression={($_.Group | select -expandproperty Value) -join '\\'}},
            @{Name='OwnerNode';Expression={($ownernode, $domain) -join '.'}},
            @{Name='IPv4';Expression={[regex]::match((ping -4 -a -n 1 $ownernode|
            select-string 'Pinging').ToString(), '(\\b\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\b)').value}}};
        $cluster_instances | % {write-host \"instances:\"($_).OwnerNode\($_).IPv4\($_).SQLInstance};
    '''

    HOSTNAME_PS_SCRIPT = '''
        $hostname = hostname; write-host \"hostname:\"$hostname;
    '''

    # ********** Always On related scripts **********
    CLUSTER_AVAILABILITY_GROUP_LIST_PS_SCRIPT = '''
        $use_cim = $PSVersionTable.PSVersion.Major -gt 2;
        if ($use_cim) {
            $domain = (get-ciminstance WIN32_ComputerSystem).Domain;
        }
        else {
            $domain = (gwmi WIN32_ComputerSystem).Domain;
        }

        Import-Module FailoverClusters;
        $results = New-Object System.Collections.Arraylist;
        $processed_ownernodes = New-Object 'system.collections.generic.dictionary[string,object]';

        $resources_dict = New-Object 'system.collections.generic.dictionary[string,object]';
        $resources_dict['ag'] = New-Object System.Collections.Arraylist;
        $resources_dict['al'] = New-Object 'system.collections.generic.dictionary[string,object]';
        $resources_dict['ips'] = New-Object 'system.collections.generic.dictionary[string,object]';
        $cluster_resources = Get-ClusterResource | Where-Object { $_.ResourceType -like 'SQL Server Availability Group' -or $_.ResourceType -like 'Network Name' -or $_.ResourceType -like 'IP Address' };
        foreach ($res in $cluster_resources) {
            if ($res.ResourceType -like 'SQL Server Availability Group') {
                $resources_dict['ag'].Add($res) > $null;
            }
            if ($res.ResourceType -like 'Network Name') {
                $resources_dict['al'][$res.Name] = $res;
            }
            if ($res.ResourceType -like 'IP Address') {
                $resources_dict['ips'][$res.Name] = $res;
            }
        }
        foreach ($resource in $resources_dict['ag']) {
            $ag_info = New-Object 'system.collections.generic.dictionary[string,object]';
            $ag_info['ag_name'] = $resource.Name;
            $ag_info['ag_resource_id'] = $resource.Id;
            $ag_info['ag_resource_state'] = $resource.State.value__;
            $ag_nodes = New-Object System.Collections.ArrayList;
            $resource_nodes = Get-ClusterOwnerNode -InputObject $resource | Select-Object -Property OwnerNodes;
            foreach ($node in $resource_nodes.OwnerNodes) {
                $owner_node_name = $node.Name.ToLower();
                $owner_node_info = $null;
                if (-not $processed_ownernodes.TryGetValue($owner_node_name, [ref]$owner_node_info)) {
                    $owner_node_info = New-Object 'system.collections.generic.dictionary[string,string]';
                    $owner_node_info['OwnerNode'] = $owner_node_name;
                    $owner_node_info['OwnerNodeFQDN'] = ($owner_node_name, $domain) -join '.';
                    $owner_node_info['OwnerNodeDomain'] = $domain;
                    $owner_node_info['IPv4'] = ([System.Net.DNS]::GetHostAddresses($owner_node_name) | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | Select-Object IPAddressToString)[0].IPAddressToString;
                    $processed_ownernodes[$owner_node_name] = $owner_node_info;
                }
                $ag_nodes.Add($owner_node_info) > $null;
            }
            $ag_info['owner_nodes_info'] = $ag_nodes;

            $listeners = New-Object System.Collections.ArrayList;
            $ag_dependency = Get-ClusterResourceDependency -InputObject $resource;
            $dep_pattern = '\(?\[([\w.\- ]+)+\]\)?';
            $search_res = $ag_dependency.DependencyExpression | Select-String -Pattern $dep_pattern -AllMatches;

            foreach ($match in $search_res.Matches) {

                if ($match.Groups.Count -gt 0) {

                    $dep_name = $match.Groups[$match.Groups.Count-1];
                    $listener = $null;
                    if ($resources_dict['al'].TryGetValue($dep_name, [ref]$listener)) {
                        $listener_info = New-Object 'system.collections.generic.dictionary[string,string]';
                        $dns_name = Get-ClusterParameter -InputObject $listener -name DnsName | Select-Object -Property Value;
                        $listener_info['id'] = $listener.Id;
                        $listener_info['ag_id'] = $resource.Id;
                        $listener_info['name'] = $listener.Name;
                        $listener_info['dns_name'] = $dns_name.Value;
                        $listener_info['state'] = $listener.State.value__;

                        $al_dependency = Get-ClusterResourceDependency -InputObject $listener;
                        if ($al_dependency.DependencyExpression -match $dep_pattern) {
                            $al_dep_name = $Matches[$Matches.Count-1];
                            $ip_address_res = $null;
                            if ($resources_dict['ips'].TryGetValue($al_dep_name, [ref]$ip_address_res)) {
                                $ip_address = Get-ClusterParameter -InputObject $ip_address_res -name Address | Select-Object -Property Value;
                                $listener_info['ip_address'] = $ip_address.Value;
                            }
                        }
                        $listeners.Add($listener_info) > $null;
                    }
                }
            }
            $ag_info['listeners_info'] = $listeners;
            $results.Add($ag_info) > $null;
        };
        $results_json = ConvertTo-Json -Depth 3 $results;
        write-host $results_json;
    '''

    ALWAYS_ON_RESOURCES_ON_NODE_PS_SCRIPT = (
        "$result = New-Object 'system.collections.generic.dictionary[string, object]';"
        "$result['hostname'] = hostname;"
        "$dictType = 'system.collections.generic.dictionary[string, object]';"
        "$result['ao_instances'] = New-Object $dictType;"
        # Get registry key for instances (with 2003 or 32/64 Bit 2008 base key)
        "$reg = [Microsoft.Win32.RegistryKey]::OpenRemoteBaseKey('LocalMachine', $hostname);"
        "$baseKeys = 'SOFTWARE\Microsoft\Microsoft SQL Server', 'SOFTWARE\Wow6432Node\Microsoft\Microsoft SQL Server';"
        "foreach ($regPath in $baseKeys) {"
        " $regKey = $reg.OpenSubKey($regPath);"
        " If ($regKey -eq $null) { Continue; };"
        # Get installed instances' names (both cluster and local)
        " If ($regKey.GetSubKeyNames() -contains 'Instance Names') {"
        "  $regKey = $reg.OpenSubKey($regpath + '\Instance Names\SQL');"
        "  $instncs = @($regkey.GetValueNames());"
        " }"
        " ElseIf ($regKey.GetValueNames() -contains 'InstalledInstances') {"
        "  $instncs = $regKey.GetValue('InstalledInstances');"
        " }"
        " Else { Continue; };"

        " $inst_list = New-Object System.Collections.Arraylist;"
        " $instncs | % {"
        "  $instValue = $regKey.GetValue($_);"
        "  $instReg = $reg.OpenSubKey($regpath + '\\' + $instValue);"
        # Get only local instances' names
        "  If ($instReg.GetSubKeyNames() -notcontains 'Cluster') {"
        "   $version = $instReg.OpenSubKey('MSSQLServer\CurrentVersion').GetValue('CurrentVersion');"
        "   $instance_ver = $_; $instance_ver += ':'; $instance_ver += $version;"
        #   Insert info about each SQL Instance into dictionary
        "   $inst_inf = New-Object 'system.collections.generic.dictionary[string,string]';"
        "   $inst_inf['name'] = $_;"
        "   $inst_inf['version'] = $version;"
        "   $inst_list.Add($inst_inf) > $null;"
        "  };"
        " };"
        " break;"
        "};"
        "$result['instances'] = $inst_list;"
        # Obtain info about Replicas and SQL Instances without touching SQL Instance
        "$agIDs = @(ag_res_ids_placeholder);"
        "foreach ($agID in $agIDs) {"
        " $agPath = \\\"Cluster\Resources\$agID\\\";"
        " $agPathKey = $reg.OpenSubKey($agPath);"
        " if ($agPathKey -eq $null) {Continue;};"
        # SQL Instances
        " if ($agPathKey.GetSubKeyNames() -contains 'SqlInstToNodeMap') {"
        "  $sqlInstnsKey = $reg.OpenSubKey($agPath + '\\' + 'SqlInstToNodeMap');"
        "  $sqlInstnsNames = $sqlInstnsKey.GetValueNames();"
        "  foreach ($insName in $sqlInstnsNames) {"
        "   $aoInstInfo = New-Object $dictType;"
        "   $aoInstInfo['sql_server_fullname'] = $insName;"
        "   $aoInstInfo['sql_server_node'] = $sqlInstnsKey.GetValue($insName);"
        "   $result['ao_instances'][$insName] = $aoInstInfo;"
        "  }"
        " }"
        "}"
        "$result_in_json = ConvertTo-Json $result;"
        "write-host $result_in_json")

    AVAILABILITY_GROUPS_INFO_PS_SCRIPT = (
        "$optimization_types = @([Microsoft.SqlServer.Management.Smo.AvailabilityGroup], [Microsoft.SqlServer.Management.Smo.Database], [Microsoft.SqlServer.Management.Smo.Table]);"
        "foreach ($ot in $optimization_types) {"
        " $def_fields = $server.GetDefaultInitFields($ot);"
        " $server.SetDefaultInitFields($ot, $def_fields);"
        "}"

        "$res = New-Object 'system.collections.generic.dictionary[string, object]';"
        "$res['ao_enabled'] = $server.IsHadrEnabled;"
        "$ags = New-Object System.Collections.ArrayList;"
        "$ars = New-Object System.Collections.ArrayList;"
        "$adbs = New-Object System.Collections.ArrayList;"

        "if ($server.IsHadrEnabled -and $server.AvailabilityGroups.Length -gt 0) {"
        " $epoch = [timezone]::CurrentTimeZone.ToLocalTime([datetime]'1/1/1970').ToUniversalTime();"
        " $dbs = $server.Databases;"
        " $ag_res_ids_map = New-Object 'system.collections.generic.dictionary[string, object]';"
        " $inst_to_node_map = New-Object 'system.collections.generic.dictionary[string, object]';"
        " $server.Refresh();"
        " $res['sql_server_fullname'] = $server.DomainInstanceName;"
        " $res['is_clustered'] = $server.IsClustered;"
        " $res['is_on_wsfc'] = $server.IsMemberOfWsfcCluster;"

        " $dbmaster = $server.Databases['master'];"

        " $cluster_query = \\\"SELECT ag_id, ag_resource_id FROM sys.dm_hadr_name_id_map;"
        " SELECT instance_name, node_name FROM sys.dm_hadr_instance_node_map;\\\";"
        " $cl_qry_res = $dbmaster.ExecuteWithResults($cluster_query);"
        " try {"
        "  foreach ($row in $cl_qry_res.tables[0].rows) {"
        "   $ag_res_ids_map[$row.ag_id] = $row.ag_resource_id;"
        "  }"
        "  foreach ($row in $cl_qry_res.tables[1].rows) {"
        "   $inst_to_node_map[$row.instance_name] = $row.node_name;"
        "  }"
        " } catch {}"
        # Availability Groups
        " foreach ($ag in $server.AvailabilityGroups) {"
        "  $ag_info = New-Object 'system.collections.generic.dictionary[string, object]';"
        "  $ag_uid = $ag.UniqueId;"
        "  $ag_res_uid = $ag_res_ids_map[$ag_uid];"
        "  $pr_rep_servr_name = $ag.PrimaryReplicaServerName;"
        "  $ag_info['name'] = $ag.Name;"
        "  $ag_info['id'] = $ag_uid;"
        "  $ag_info['ag_res_id'] = $ag_res_uid;"
        "  $ag_info['primary_replica_server_name'] = $pr_rep_servr_name;"
        "  $ag_info['is_distributed'] = $ag.IsDistributedAvailabilityGroup;"
        "  $ag_info['health_check_timeout'] = $ag.HealthCheckTimeout;"
        "  $ag_info['automated_backup_preference'] = $ag.AutomatedBackupPreference;"
        "  $ag_info['failure_condition_level'] = $ag.FailureConditionLevel;"
        "  $ag_info['cluster_type'] = $ag.ClusterTypeWithDefault;"
        "  $ag_info['db_level_health_detection'] = $ag.DatabaseHealthTrigger;"
        "  $ags.Add($ag_info) > $null;"
        # Availability Replicas
        "  foreach ($ar in $ag.AvailabilityReplicas) {"
        "   $ar_inf = New-Object 'System.Collections.Generic.Dictionary[string, object]';"
        "   $ar_uid = $ar.UniqueId;"
        "   $ar_inf['ag_id'] = $ag_uid;"
        "   $ar_inf['ag_res_id'] = $ag_res_uid;"
        "   $ar_inf['id'] = $ar_uid;"
        "   $ar_inf['name'] = $ar.Name;"
        "   $ar_inf['endpoint_url'] = $ar.EndpointUrl;"
        "   $ar_info_query = \\\"SELECT availability_replicas.replica_server_name AS rep_srv_name"
        "   FROM sys.availability_replicas AS availability_replicas"
        "   WHERE availability_replicas.replica_id = '$ar_uid';\\\";"
        "   $ar_info_res = $dbmaster.ExecuteWithResults($ar_info_query);"
        "   try {"
        "    $ar_inf['replica_server_name'] = $ar_info_res.tables[0].rows[0].rep_srv_name;"
        "   }"
        "   catch {}"
        "   try {$ar_inf['replica_server_hostname'] = $inst_to_node_map[$ar_inf['replica_server_name']];} catch {}"
        "   $ars.Add($ar_inf) > $null;"
        "  }"
        # Availability Databases
        "  foreach ($adb in $ag.AvailabilityDatabases) {"
        "   $adb_inf = New-Object 'System.Collections.Generic.Dictionary[string, object]';"
        "   $adb_inf['adb_id'] = $adb.UniqueId;"
        "   $adb_inf['ag_res_id'] = $ag_res_uid;"
        "   $adb_inf['name'] = $adb.Name;"
        "   $adb_inf['sync_state'] = $adb.SynchronizationState;"
        "   $adb_inf['suspended'] = $adb.IsSuspended;"
        "   $db = $dbs | Where-Object {$_.AvailabilityGroupName -EQ $ag.Name -and $_.Name -EQ $adb.Name};"
        "   $adb_inf['version'] = $db.Version;"
        "   $adb_inf['isaccessible'] = $db.IsAccessible;"
        "   $adb_inf['db_id'] = $db.ID;"
        "   $adb_inf['owner'] = $db.Owner;"
        "   $adb_inf['lastbackupdate'] = (New-TimeSpan -Start $epoch -End $db.LastBackupDate).TotalSeconds;"
        "   $adb_inf['collation'] = $db.Collation;"
        "   $adb_inf['createdate'] = (New-TimeSpan -Start $epoch -End $db.CreateDate).TotalSeconds;"
        "   $adb_inf['defaultfilegroup'] = $db.DefaultFileGroup;"
        "   $adb_inf['primaryfilepath'] = $db.PrimaryFilePath;"
        "   $adb_inf['lastlogbackupdate'] = (New-TimeSpan -Start $epoch -End $db.LastLogBackupDate).TotalSeconds;"
        "   $adb_inf['systemobject'] = $db.IsSystemObject;"
        "   $adb_inf['recoverymodel'] = $db.DatabaseOptions.RecoveryModel;"
        "   $adbs.Add($adb_inf) > $null;"
        "  }"
        " }"
        "}"
        "$res['availability_groups'] = $ags;"
        "$res['availability_replicas'] = $ars;"
        "$res['availability_databases'] = $adbs;"
        "$res_json = ConvertTo-Json $res;"
        "Write-Host $res_json")
    # **********

    def get_instances_names(self, is_cluster):
        """Run script to retrieve DB instances' names and hostname either
        available in the cluster or installed on the local machine,
        according to the 'is_cluster' parameter supplied.
        """
        psinstance_script = self.CLUSTER_INSTANCES_PS_SCRIPT if is_cluster \
            else self.LOCAL_INSTANCES_PS_SCRIPT
        return self.run_command(
            psinstance_script + self.HOSTNAME_PS_SCRIPT
        )

    def get_always_on_resources_on_node(self, ag_resource_ids):
        """
        Run script to get information about SQL Server Always On resources on Windows nodes
        @param ag_resource_ids: Iterable with Awailability Group cluster resource IDs.
        @type ag_resource_ids: iterable
        @return: CommandResponse:
            .stdout = [<non-empty, stripped line>, ...]
            .stderr = [<non-empty, stripped line>, ...]
            .exit_code = <int>
        @rtype: txwinrm.shell.CommandResponse
        """
        instance_ps_script = self.ALWAYS_ON_RESOURCES_ON_NODE_PS_SCRIPT
        instance_ps_script = instance_ps_script.replace('ag_res_ids_placeholder',
                                                        ','.join(("'{}'".format(ag_id) for ag_id in ag_resource_ids)))
        return self.run_command(
            instance_ps_script
        )

    def get_availability_group_cluster_resources(self):
        """
        Run script to get information about Windows nodes
        on which SQL Instance with Always On (AO) resources are placed.

        @return: CommandResponse:
            .stdout = [<non-empty, stripped line>, ...]
            .stderr = [<non-empty, stripped line>, ...]
            .exit_code = <int>
        @rtype: txwinrm.shell.CommandResponse
        """
        ag_ps_script = self.CLUSTER_AVAILABILITY_GROUP_LIST_PS_SCRIPT
        return self.run_command(
            ag_ps_script
        )

    def get_availability_group_info(self, sql_connection, sql_server_version):
        """
        Run script to get information about Always On (AO) resources on provided SQL Instance.

        @param sql_connection: List with strings which in whole forms SQL Instance connection string.
        @type sql_connection: list
        @param sql_server_version: SQL Server version.
        @type sql_server_version: int

        @return: CommandResponse:
            .stdout = [<non-empty, stripped line>, ...]
            .stderr = [<non-empty, stripped line>, ...]
            .exit_code = <int>
        @rtype: txwinrm.shell.CommandResponse
        """
        script_prefix = ''.join(getSQLAssembly(sql_server_version) +
                                sql_connection)
        ag_ps_info_script = self.AVAILABILITY_GROUPS_INFO_PS_SCRIPT

        return self.run_command(script_prefix + ag_ps_info_script)

    @defer.inlineCallbacks
    def run_command(self, pscommand):
        """Run PowerShell command."""
        buffer_size = ('$Host.UI.RawUI.BufferSize = New-Object '
                       'Management.Automation.Host.Size (4096, 512);')
        script = "\"& {{{0} {1}}}\"".format(
            buffer_size, pscommand.replace('\n', ' '))
        self.log.debug(script)
        results = yield self.winrs.run_command(self.PS_COMMAND, ps_script=script)
        defer.returnValue(results)


class WinMSSQL(WinRMPlugin):

    deviceProperties = WinRMPlugin.deviceProperties + (
        'zDBInstances',
        'getDeviceClassName',
        'zSQLAlwaysOnEnabled'
    )

    @staticmethod
    def parse_zDBInstances(zDBInstances_value, username, password):

        db_logins = {}

        dbinstance = json.loads(zDBInstances_value)
        users = [el.get('user') for el in filter(None, dbinstance)]
        if ''.join(users):
            for el in filter(None, dbinstance):
                db_logins[el.get('instance')] = dict(
                    username=el.get('user') if el.get('user') else username,
                    password=el.get('passwd') if el.get('passwd') else password,
                    login_as_user=False if el.get('user') else True
                )
        else:
            for el in filter(None, dbinstance):
                db_logins[el.get('instance')] = dict(
                    username=username,
                    password=password,
                    login_as_user=True
                )
        return db_logins

    @staticmethod
    def get_sql_instance_credentials(db_logins, instance_name, win_username, win_password):
        # Look for specific instance creds first
        try:
            sql_username = db_logins[instance_name]['username']
            sql_password = db_logins[instance_name]['password']
            login_as_user = db_logins[instance_name]['login_as_user']
        except KeyError:
            # Try default MSSQLSERVER creds
            try:
                sql_username = db_logins['MSSQLSERVER']['username']
                sql_password = db_logins['MSSQLSERVER']['password']
                login_as_user = db_logins['MSSQLSERVER']['login_as_user']
            except KeyError:
                # Use windows auth
                sql_username = win_username
                sql_password = win_password
                login_as_user = True

        return sql_username, sql_password, login_as_user

    @defer.inlineCallbacks
    def collect_ao_info_on_sql_instance(self, connection_info, instance_hostname, host_username,
                                        host_password, instance_info, sql_logins, additional_data, log):
        """
        Collects information about Always On (AO) resources on provided SQL Instance.

        @param connection_info: Information needed to instantiate SQLCommander object.
        @type connection_info: txwinrm.collect.ConnectionInfo
        @param instance_hostname: SQL Instance Owner node hostname.
        @type instance_hostname: str
        @param host_username: Windows host username.
        @type host_username: str
        @param host_password: Windows host password.
        @type host_password: str
        @param instance_info: Dictionary with SQL Instance name and version.
        @type instance_info: dict
        @param sql_logins: Dictionary with SQL Instances and theirs credentials.
        @type sql_logins: dict
        @param additional_data: Additional data provided to the method.
        @type additional_data: dict
        @param log: logger.
        @type log: logger

        @return: Always On reslources on given Windows machine in format:
            {
                'errors': defaultdict(list),
                'sql_instances': defaultdict(dict),
                'availability_groups': defaultdict(dict),
                'availability_replicas': defaultdict(dict),
                'availability_databases': defaultdict(dict)
            }
        @rtype: dict
        """
        results = {
            'errors': defaultdict(list),
            'sql_instances': defaultdict(dict),
            'availability_groups': defaultdict(dict),
            'availability_replicas': defaultdict(dict),
            'availability_databases': defaultdict(dict)
        }

        winrs = SQLCommander(connection_info, log)
        instance = instance_info.get('name', '').strip()
        sql_server_version = instance_info.get('version')

        if instance not in sql_logins:
            log.debug("DB Instance {0} found but was not set in zDBInstances.  "
                      "Using default credentials.".format(instance))

        # TODO: it seems that Always On instances are placed only on local SQL instances, not cluster ones.
        #  Need to check, though. Currently assuming that they are.
        instance_title, sqlserver = get_sql_instance_naming_info(instance_name=instance, hostname=instance_hostname)

        sql_username, sql_password, login_as_user = self.get_sql_instance_credentials(sql_logins, instance,
                                                                                      host_username,host_password)
        sql_version = int(sql_server_version.split('.')[0])
        sql_connection = SqlConnection(sqlserver, sql_username, sql_password, login_as_user, sql_version).sqlConnection

        ag_info_response = yield winrs.get_availability_group_info(sql_connection, sql_version)

        log.debug('Availability Groups info response for SQL Instance {} : {}'.format(instance, ag_info_response))

        check_username(ag_info_response, instance, log)
        ag_info_stdout = filter_sql_stdout(ag_info_response.stdout)
        availability_groups_info, passing_error = parse_winrs_response(ag_info_stdout, 'json')

        if not availability_groups_info and passing_error:
            results['errors'][sqlserver].append('Error during parsing Availability Groups info response: {}'.format(passing_error))
        else:
            ao_enabled = availability_groups_info.get('ao_enabled', False)
            ao_ag_count = availability_groups_info.get('ao_enabled', 0)
            # Take only those SQL instances which have Availability Groups on them.
            # Just enabled Always On not enough.
            if ao_enabled is True and ao_ag_count > 0:

                # 1. SQL Instances
                sql_server_instance_full_name = availability_groups_info.get('sql_server_fullname') or sqlserver

                recursive_mapping_update(
                    results['sql_instances'][sql_server_instance_full_name],
                    {
                        'sql_server_instance_full_name': sql_server_instance_full_name,
                        'instance_original_name': instance,  # Like 'MSSQLSERVER' for default instances. Keep this name.
                        'instance_name': instance_title,
                        'sql_server_name': sqlserver,
                        'sql_server_version': sql_server_version,
                        'is_clustered_instance': availability_groups_info.get('is_clustered', False),
                        'is_on_wsfc': availability_groups_info.get('is_on_wsfc', False),
                        'sqlhostname': instance_hostname,
                        # update SQL Instance Info with Windows node-level info
                        'sql_hostname_fqdn': additional_data.get('sql_hostname_fqdn', ''),
                        'sql_host_ip': additional_data.get('sql_host_ip', ''),
                    }
                )

                # 2. Availability Groups. Information about Always On Availability Groups on SQL Instance.
                instance_ags = availability_groups_info.get('availability_groups', [])
                for ag_info in instance_ags:
                    ag_res_id = ag_info.get('ag_res_id')
                    if not ag_res_id:
                        continue
                    recursive_mapping_update(
                        results['availability_groups'][ag_res_id],
                        ag_info
                    )

                # 3. Availability Replicas.
                ag_owner_node_domain = additional_data.get('ag_owner_node_domain', '')
                availability_replicas = availability_groups_info.get('availability_replicas', [])
                for ar_info in availability_replicas:
                    ar_id = ar_info.get('id')
                    if not ar_id:
                        continue
                    recursive_mapping_update(
                        results['availability_replicas'][ar_id],
                        ar_info
                    )

                    # Also update SQL Instance info with Availability Replicas SQL Instance (SQL Instances from another
                    # replica nodes, which we haven't collected yet)
                    replica_server_name = ar_info.get('replica_server_name', '')
                    if replica_server_name:

                        replica_server_name_parts = replica_server_name.split('\\')
                        replica_instance_original_name = replica_server_name_parts[-1] if len(replica_server_name_parts) > 0 \
                            else replica_server_name

                        replica_server_hostname = ar_info.get('replica_server_hostname', '')
                        replica_hostname_fqdn = ''
                        if replica_server_hostname and ag_owner_node_domain:
                            replica_hostname_fqdn = '{}.{}'.format(replica_server_hostname, ag_owner_node_domain)

                        replica_instance_original_name = get_sql_instance_original_name(replica_instance_original_name,
                                                                                        replica_server_hostname)

                        instance_title, _ = get_sql_instance_naming_info(instance_name=replica_instance_original_name,
                                                                         hostname=replica_server_hostname)

                        recursive_mapping_update(
                            results['sql_instances'][replica_server_name],
                            {
                                'sql_server_instance_full_name': replica_server_name,
                                'sql_server_name': replica_server_name,
                                'instance_name': instance_title,
                                'sqlhostname': replica_server_hostname,
                                'instance_original_name': replica_instance_original_name,
                                'sql_hostname_fqdn': replica_hostname_fqdn
                            }
                        )

                # 4. Availability Databases.
                availability_databases = availability_groups_info.get('availability_databases', [])
                for database_info in availability_databases:
                    db_id = database_info.get('db_id')  # database index (e.g. 1, 2)
                    if not db_id:
                        continue
                    recursive_mapping_update(
                        # Because DB IDs are not unique across different SQL Instances, DB key is tuple
                        results['availability_databases'][(sql_server_instance_full_name, db_id)],
                        database_info
                    )

        # stderr
        if ag_info_response.stderr:
            results['errors'][sqlserver].append(get_console_output_from_parts(ag_info_response.stderr))

        defer.returnValue(results)

    @defer.inlineCallbacks
    def collect_ao_info_on_node(self, ag_owner_node, connection_info, host_username,
                                host_password, sql_logins, additional_data, log):
        """
        Collects information about Always On (AO) resources on provided Windows node which is Availability Group
        (AG) owner node.

        @param ag_owner_node: Information about Availability Group (AG) owner node.
            Tuple: ('OwnerNode', 'OwnerNodeFQDN', 'OwnerNodeDomain', 'IPv4')
        @type ag_owner_node: tuple
        @param connection_info: Information needed to instantiate SQLCommander object.
        @type connection_info: txwinrm.collect.ConnectionInfo
        @param sql_logins: Dictionary with SQL Instances and theirs credentials.
        @type sql_logins: dict
        @param host_username: Windows host username.
        @type host_username: str
        @param host_password: Windows host password.
        @type host_password: str
        @param additional_data: Additional data provided to the method.
        @type additional_data: dict
        @param log: logger.
        @type log: logger

        @return: Always On reslources on given Windows machine in format:
            {
                'errors': defaultdict(list),
                'sql_instances': defaultdict(dict),
                'availability_groups': defaultdict(dict),
                'availability_replicas': defaultdict(dict),
                'availability_databases': defaultdict(dict)
            }
        @rtype: dict
        """
        results = {
            'errors': defaultdict(list),
            'sql_instances': defaultdict(dict),
            'availability_groups': defaultdict(dict),
            'availability_replicas': defaultdict(dict),
            'availability_databases': defaultdict(dict)
        }

        ag_owner_node_name, ag_owner_node_fqdn, ag_owner_node_domain, ag_owner_node_ip_address = ag_owner_node
        ag_owner_node_name = ag_owner_node_name.strip()
        ag_owner_node_fqdn = ag_owner_node_fqdn.strip()
        ag_owner_node_domain = ag_owner_node_domain.strip()
        ag_owner_node_ip_address = ag_owner_node_ip_address.strip()

        if not ag_owner_node_fqdn:
            log.error("Empty connection info for node {}".format(ag_owner_node_fqdn))
            defer.returnValue(results)
        # create separate remote shell for Windows node
        winrs = None
        try:
            connection_info = connection_info._replace(hostname=ag_owner_node_fqdn)
            if ag_owner_node_ip_address:
                connection_info = connection_info._replace(ipaddress=ag_owner_node_ip_address)
            else:
                connection_info = connection_info._replace(ipaddress=ag_owner_node_fqdn)
            winrs = SQLCommander(connection_info, log)
        except Exception as e:  # NOQA: catch broad Exception because WinRMClients' connection info verification raises it.
            log.error('Malformed data returned for node {}. {}'.format(ag_owner_node_fqdn, e.message))
            defer.returnValue(results)

        # provide AG ids to script
        ag_res_ids = additional_data.get('ag_res_ids', [])

        instances_info_response = yield winrs.get_always_on_resources_on_node(ag_res_ids)

        log.debug("Always On Instances info response on node {}: {}".format(ag_owner_node_fqdn,
                                                                            instances_info_response.stdout +
                                                                            instances_info_response.stderr))

        instances_info, passing_error = parse_winrs_response(instances_info_response.stdout, 'json')

        if not instances_info and passing_error:
            results['errors'] = {'error': 'Error during parsing instances info info: {}'.format(
                instances_info_response.stderr)}
            defer.returnValue(results)

        hostname = instances_info.get('hostname', '')
        instances = instances_info.get('instances', [])
        ao_instances = instances_info.get('ao_instances', {})

        if not instances:
            log.warn('No MSSQL Instances were found on node {}'.format(ag_owner_node_fqdn))
            defer.returnValue(results)

        # Update Instances information
        recursive_mapping_update(
            results['sql_instances'],
            ao_instances
        )

        # set IP
        for sql_instance_name, sql_instance_info in results['sql_instances'].iteritems():
            if isinstance(sql_instance_info, dict):
                sql_server_node = sql_instance_info.get('sql_server_node', '')
                sql_server_node_fqdn = '{}.{}'.format(sql_server_node, ag_owner_node_domain)
                sql_instance_node_ip = additional_data['nodes_info'].get(sql_server_node_fqdn, {}).get('ip_v4')
                if sql_instance_node_ip:
                    results['sql_instances'][sql_instance_name]['sql_host_ip'] = sql_instance_node_ip

        # set SQL Instance version
        for instance_info in instances:
            sql_instance_name = instance_info.get('name', '').strip()
            if sql_instance_name:
                _, sqlserver_full_name = get_sql_instance_naming_info(instance_name=sql_instance_name,
                                                                      hostname=hostname.upper())
                sql_instance_version = instance_info.get('version')
                if sqlserver_full_name in results['sql_instances'] and sql_instance_version is not None:
                    results['sql_instances'][sqlserver_full_name]['sql_server_version'] = sql_instance_version

        # Get info about primary replica SQL Instance for each availability group, because only on this instance we
        # can utilize SMO/T-SQL for getting info about Always On stuff.
        # Use DeferredList to perform asynchronous collection per each SQL Instance.
        additional_data = {
            'sql_hostname_fqdn': ag_owner_node_fqdn,
            'sql_host_ip': ag_owner_node_ip_address,
            'ag_owner_node_domain': ag_owner_node_domain
        }

        ao_info_deffereds = []
        for instance_info in instances:
            ag_info_deffered = self.collect_ao_info_on_sql_instance(connection_info, hostname, host_username, host_password,
                                                                    instance_info, sql_logins, additional_data, log)
            ao_info_deffereds.append(ag_info_deffered)

        collection_results = yield defer.DeferredList(ao_info_deffereds, consumeErrors=True)

        for success, ag_info_response in collection_results:

            if not success:
                results['errors'][ag_owner_node_fqdn].append(ag_info_response.getErrorMessage())
                continue

            recursive_mapping_update(
                results['sql_instances'],
                ag_info_response.get('sql_instances', {})
            )
            recursive_mapping_update(
                results['availability_groups'],
                ag_info_response.get('availability_groups', {})
            )
            recursive_mapping_update(
                results['availability_replicas'],
                ag_info_response.get('availability_replicas', {})
            )
            recursive_mapping_update(
                results['availability_databases'],
                ag_info_response.get('availability_databases', {})
            )

            ag_errors = ag_info_response.get('errors')
            if ag_errors:
                results['errors'][ag_owner_node_fqdn].append(ag_errors)

        defer.returnValue(results)

    @defer.inlineCallbacks
    def collect_ao_info(self, winrs, connection_info, sql_logins, host_username, host_password, log):
        """
        Collects information about Always On (AO) resources on provided Windows machine.

        @param winrs: Connction object which incapsulate all necessary winrs capability and MS SQL commands.
        @type winrs: ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.WinMSSQL.SQLCommander
        @param connection_info: Information needed to instantiate SQLCommander object.
        @type connection_info: txwinrm.collect.ConnectionInfo
        @param sql_logins: Dictionary with SQL Instances and theirs credentials.
        @type sql_logins: dict
        @param host_username: Windows host username.
        @type host_username: str
        @param host_password: Windows host password.
        @type host_password: str
        @param log: logger.
        @type log: logger

        @return: Always On reslources on given Windows machine in format:
            {
                'errors': defaultdict(list),
                'sql_instances': defaultdict(dict),
                'availability_groups': defaultdict(dict),
                'availability_replicas': defaultdict(dict),
                'availability_listeners': defaultdict(dict),
                'availability_databases': defaultdict(dict)
            }
        @rtype: dict
        """
        results = {
            'errors': defaultdict(list),
            'sql_instances': defaultdict(dict),
            'availability_groups': defaultdict(dict),
            'availability_replicas': defaultdict(dict),
            'availability_listeners': defaultdict(dict),
            'availability_databases': defaultdict(dict)
        }

        # Get information about Availability Groups, theirs owner nodes and Availability Group listeners.
        ag_cluster_resources_response = yield winrs.get_availability_group_cluster_resources()

        if not ag_cluster_resources_response:
            log.info('{}: No output while getting Availability Groups cluster resources.'
                     '  zWinRMEnvelopeSize may not be large enough.'
                     '  Increase the size and try again.'.format(self.name()))
            defer.returnValue(results)

        log.debug('{} modeler Availability Groups cluster resources results: {}'.format(self.name(),
                                                                                        ag_cluster_resources_response))

        ag_cluster_resources, passing_error = parse_winrs_response(ag_cluster_resources_response.stdout, 'json')

        if not ag_cluster_resources and passing_error:
            results['errors']['error'].append('Error during parsing available group list info: {}'.format(
                ag_cluster_resources_response.stderr))
            defer.returnValue(results)

        if isinstance(ag_cluster_resources, list) and len(ag_cluster_resources) == 0:
            results['errors']['error'].append('No MSSQL Availability groups are present')
            defer.returnValue(results)

        # Fill results with available information
        ag_owner_nodes_info = set()  # use set to avoid owner nodes duplication (several AGs may be placed on same node)
        nodes_info = {}  # additional info per node to provide for each collection coroutine
        ag_res_ids = set()  # Availability Group cluster resource IDs to use in further collection
        for ag_info in ag_cluster_resources:
            ag_resource_id = ag_info.get('ag_resource_id')
            if not ag_resource_id:
                continue
            results['availability_groups'][ag_resource_id]['ag_res_id'] = ag_resource_id
            results['availability_groups'][ag_resource_id]['name'] = ag_info.get('ag_name')
            results['availability_groups'][ag_resource_id]['cluster_resource_state'] = ag_info.get('ag_resource_state')
            ag_res_ids.add(ag_resource_id)
            # Owner nodes info
            owner_nodes_info = ag_info.get('owner_nodes_info')
            if isinstance(owner_nodes_info, list):
                for owner_node_info in owner_nodes_info:
                    owner_node_fqdn = owner_node_info.get('OwnerNodeFQDN', '')
                    ag_owner_nodes_info.add((owner_node_info.get('OwnerNode', ''),
                                             owner_node_fqdn,
                                             owner_node_info.get('OwnerNodeDomain', ''),
                                             owner_node_info.get('IPv4', '')))
                    if owner_node_fqdn:
                        nodes_info[owner_node_fqdn] = {'ip_v4': owner_node_info.get('IPv4', '')}
            # Availability Group listeners info
            listeners_info = ag_info.get('listeners_info')
            if isinstance(listeners_info, list):
                for listener in listeners_info:
                    listener_id = listener.get('id')
                    if not listener_id:
                        continue
                    results['availability_listeners'][listener_id]['id'] = listener_id
                    results['availability_listeners'][listener_id]['name'] = listener.get('name')
                    results['availability_listeners'][listener_id]['dns_name'] = listener.get('dns_name')
                    results['availability_listeners'][listener_id]['state'] = listener.get('state')
                    results['availability_listeners'][listener_id]['ag_id'] = listener.get('ag_id')
                    results['availability_listeners'][listener_id]['ip_address'] = listener.get('ip_address')

        # Provide additional data to each collect coroutine
        additional_data = {
            'ag_res_ids': ag_res_ids,
            'nodes_info': nodes_info
        }

        # Collect SQL Instances info on each Availability Groups' possible Owner Node.
        # Use DeferredList to perform asynchronous collection per each Windows node.
        ao_info_deferreds = []
        for ag_owner_node in ag_owner_nodes_info:
            ao_info_deffer = self.collect_ao_info_on_node(ag_owner_node, connection_info, host_username,
                                                          host_password, sql_logins, additional_data, log)
            ao_info_deferreds.append(ao_info_deffer)

        collection_results = yield defer.DeferredList(ao_info_deferreds, consumeErrors=True)
        log.debug('Always On resources on nodes: {}'.format(collection_results))

        for success, ag_info_response in collection_results:

            if not success:
                results['errors']['err'].append(ag_info_response.getErrorMessage())
                continue

            recursive_mapping_update(
                results['sql_instances'],
                ag_info_response.get('sql_instances', {})
            )
            recursive_mapping_update(
                results['availability_groups'],
                ag_info_response.get('availability_groups', {})
            )
            recursive_mapping_update(
                results['availability_replicas'],
                ag_info_response.get('availability_replicas', {})
            )
            recursive_mapping_update(
                results['availability_databases'],
                ag_info_response.get('availability_databases', {})
            )

            ag_errors = ag_info_response.get('errors')
            if ag_errors:
                results['errors']['err'].append(ag_errors)

        defer.returnValue(results)

    @defer.inlineCallbacks
    def collect(self, device, log):
        self.log = log
        # Check if the device is a cluster device.
        isCluster = True if 'Microsoft/Cluster' in device.getDeviceClassName \
            else False
        use_ao = use_sql_always_on(device)

        dbinstance = prepare_zDBInstances(device.zDBInstances)
        username = device.windows_user
        password = device.windows_password
        dblogins = {}
        eventmessage = 'Error parsing zDBInstances'
        ao_info = {}  # Parsed response about Always On (AO) resources
        ao_instances_info = {}  # Contains  result about Always On (AO) resources

        try:
            dblogins = self.parse_zDBInstances(dbinstance, username, password)
            results = {'clear': eventmessage}
        except (ValueError, TypeError, IndexError):
            # Error with dbinstance names or password
            results = {'error': eventmessage}
            defer.returnValue(results)

        conn_info = self.conn_info(device)
        conn_info = conn_info._replace(timeout=device.zCollectorClientTimeout - 5)
        winrs = SQLCommander(conn_info, log)

        dbinstances = winrs.get_instances_names(isCluster)
        instances = yield dbinstances

        # Get information about SQL Instances on which Always On Availability groups are placed
        if use_ao:
            ao_info = yield self.collect_ao_info(winrs, conn_info, dblogins, username, password, log)
            log.debug('Always On resources: {}'.format(ao_info))
            ao_instances_info = ao_info.get('sql_instances', [])

        maps = {}
        if not instances and not ao_instances_info:
            log.info('{}:  No output while getting instance names.'
                     '  zWinRMEnvelopeSize may not be large enough.'
                     '  Increase the size and try again.'.format(self.name()))
            defer.returnValue(maps)

        maps['errors'] = {}
        log.debug('WinMSSQL modeler get_instances_names results: {}'.format(instances))
        instance_oms = []
        database_oms = []
        backup_oms = []
        jobs_oms = []
        server_config = {}
        sqlhostname = ''

        for serverconfig in instances.stdout:
            key, value = serverconfig.split(':', 1)
            if key == 'instances':
                serverlist = {}
            else:
                serverlist = []
            if not value:
                continue
            if key in server_config:
                serverlist = server_config[key]
            if key == 'instances':
                instance_version = value.split(':')
                if len(instance_version) > 1:
                    serverlist[''.join(instance_version[:-1]).strip()] = ''.join(instance_version[-1:]).strip()
                else:
                    serverlist[value.strip()] = '0'
            else:
                serverlist.append(value.strip())
            server_config[key] = serverlist

        instances_info = server_config.get('instances', {})

        if not instances_info and not ao_instances_info:
            eventmessage = 'No MSSQL Servers are installed but modeler is enabled'
            results = {'error': eventmessage}
            defer.returnValue(results)

        sqlhostname = server_config['hostname'][0]
        # Set value for device sqlhostname property
        device_om = ObjectMap()
        device_om.sqlhostname = sqlhostname
        for instance, version in instances_info.items():
            owner_node = ''  # Leave empty for local databases.
            ip_address = None # Leave empty for local databases.
            # For cluster device, create a new a connection to each node,
            # which owns network instances.
            if isCluster:
                try:
                    owner_node, ip_address, sql_server, instance = instance.split('\\')
                    owner_node = owner_node.strip()
                    sql_server = sql_server.strip()
                    instance = instance.strip()
                    ip_address = ip_address.strip()
                    conn_info = conn_info._replace(hostname=owner_node)
                    if ip_address:
                        conn_info = conn_info._replace(ipaddress=ip_address)
                    else:
                        conn_info = conn_info._replace(ipaddress=owner_node)
                    winrs = SQLCommander(conn_info, log)
                except ValueError:
                    log.error('Malformed data returned for instance {}'.format(
                        instance))
                    continue

            if instance not in dblogins:
                log.debug("DB Instance {0} found but was not set in zDBInstances.  "
                          "Using default credentials.".format(instance))

            instance_title = instance
            if instance == 'MSSQLSERVER':
                instance_title = sqlserver = sqlhostname
            else:
                sqlserver = '{0}\{1}'.format(sqlhostname, instance)

            if isCluster:
                if instance == 'MSSQLSERVER':
                    instance_title = sqlserver = sql_server
                else:
                    sqlserver = '{0}\{1}'.format(sql_server, instance)

            om_instance = ObjectMap()
            om_instance.id = self.prepId(instance_title)
            if instance == 'MSSQLSERVER':
                om_instance.perfmon_instance = 'SQLServer'
                om_instance.title = '{}(MSSQLSERVER)'.format(instance_title)
            else:
                om_instance.perfmon_instance = 'MSSQL${}'.format(instance)
                om_instance.title = instance_title
            om_instance.instancename = instance
            om_instance.sql_server_version = version
            om_instance.cluster_node_server = '{0}//{1}'.format(
                owner_node, sqlserver)
            om_instance.owner_node_ip = ip_address

            instance_oms.append(om_instance)

            sqlusername, sqlpassword, login_as_user = self.get_sql_instance_credentials(dblogins, instance, username,
                                                                                        password)

            sql_version = int(om_instance.sql_server_version.split('.')[0])
            sqlConnection = SqlConnection(sqlserver, sqlusername, sqlpassword, login_as_user, sql_version).sqlConnection

            db_sqlConnection = []
            # Get database information
            # smo optimization for faster loading
            db_sqlConnection.append("$ob = New-Object Microsoft.SqlServer.Management.Smo.Database;"
                                    "$def = $server.GetDefaultInitFields($ob.GetType());"
                                    "$server.SetDefaultInitFields($ob.GetType(), $def);")
            db_sqlConnection.append('write-host "====Databases";')
            db_sqlConnection.append('$server.Databases | foreach {'
                                    'write-host \"Name---\" $_,'
                                    '\"`tVersion---\" $_.Version,'
                                    '\"`tIsAccessible---\" $_.IsAccessible,'
                                    '\"`tID---\" $_.ID,'
                                    '\"`tOwner---\" $_.Owner,'
                                    '\"`tLastBackupDate---\" $_.LastBackupDate,'
                                    '\"`tCollation---\" $_.Collation,'
                                    '\"`tCreateDate---\" $_.CreateDate,'
                                    '\"`tDefaultFileGroup---\" $_.DefaultFileGroup,'
                                    '\"`tPrimaryFilePath---\" $_.PrimaryFilePath,'
                                    '\"`tLastLogBackupDate---\" $_.LastLogBackupDate,'
                                    '\"`tSystemObject---\" $_.IsSystemObject,'
                                    '\"`tRecoveryModel---\" $_.DatabaseOptions.RecoveryModel'
                                    '};')

            # Get SQL Backup Jobs information
            backup_sqlConnection = []
            # smo optimization for faster loading
            backup_sqlConnection.append("$ob = New-Object Microsoft.SqlServer.Management.Smo.BackupDevice;"
                                        "$def = $server.GetDefaultInitFields($ob.GetType());"
                                        "$server.SetDefaultInitFields($ob.GetType(), $def);")
            backup_sqlConnection.append('write-host "====Backups";')
            # Get database information
            backup_sqlConnection.append('try{$server.BackupDevices | foreach {'
                                        'write-host \"Name---\" $_.Name,'
                                        '\"`tDeviceType---\" $_.BackupDeviceType,'
                                        '\"`tPhysicalLocation---\" $_.PhysicalLocation,'
                                        '\"`tStatus---\" $_.State'
                                        '}}catch{ continue };')

            # Get SQL Jobs information
            job_sqlConnection = []
            # smo optimization for faster loading
            job_sqlConnection.append("$ob = New-Object Microsoft.SqlServer.Management.Smo.Agent.Job;"
                                     "$def = $server.GetDefaultInitFields($ob.GetType());"
                                     "$server.SetDefaultInitFields($ob.GetType(), $def);")
            job_sqlConnection.append('write-host "====Jobs";')
            job_sqlConnection.append("try {")
            job_sqlConnection.append("$server.JobServer.Jobs | foreach {")
            job_sqlConnection.append('write-host \"job_jobname---\" $_.Name,')
            job_sqlConnection.append('\"job_enabled---\" $_.IsEnabled,')
            job_sqlConnection.append('\"job_jobid---\" $_.JobID,')
            job_sqlConnection.append('\"job_description---\" $_.Description,')
            job_sqlConnection.append('\"job_datecreated---\" $_.DateCreated,')
            job_sqlConnection.append('\"job_username---\" $_.OwnerLoginName')
            job_sqlConnection.append("}}catch { continue; }")

            version_sqlConnection = []
            if isCluster:
                version_sqlConnection.append("write-host \"====Version\";")
                version_sqlConnection.append("$dbmaster = $server.Databases['master'];")
                version_sqlConnection.append('$query = \\"SELECT SERVERPROPERTY(\'productversion\') as version\\";')
                version_sqlConnection.append("$res = $dbmaster.ExecuteWithResults($query);")
                version_sqlConnection.append("write-host $res.tables[0].rows[0].version;")

            instance_info = yield winrs.run_command(
                ''.join(getSQLAssembly(int(om_instance.sql_server_version.split('.')[0])) +
                        sqlConnection + db_sqlConnection +
                        backup_sqlConnection + job_sqlConnection + version_sqlConnection)
            )

            log.debug('Modeling databases, backups, jobs results:  {}'.format(instance_info))
            check_username(instance_info, instance, log)
            maps['errors'][om_instance.id] = instance_info.stderr
            stdout = filter_sql_stdout(instance_info.stdout)
            try:
                db_index = stdout.index('====Databases')
            except ValueError:
                db_index = None
            try:
                backup_index = stdout.index('====Backups')
            except ValueError:
                backup_index = None
            try:
                job_index = stdout.index('====Jobs')
            except ValueError:
                job_index = None
            try:
                version_index = stdout.index('====Version')
            except ValueError:
                version_index = None
            if db_index is not None and backup_index is not None:
                for stdout_line in stdout[db_index + 1:backup_index]:
                    if stdout_line == 'assembly load error':
                        break
                    om_database = self.get_db_om(om_instance,
                                                 instance,
                                                 owner_node,
                                                 sqlserver,
                                                 stdout_line)
                    if om_database:
                        database_oms.append(om_database)
            if backup_index is not None and job_index is not None:
                for stdout_line in stdout[backup_index + 1:job_index]:
                    om_backup = self.get_backup_om(om_instance,
                                                   instance,
                                                   stdout_line)
                    if om_backup:
                        backup_oms.append(om_backup)

            if job_index is not None:
                job_line = ''
                for stdout_line in stdout[job_index + 1:]:
                    # account for newlines in description
                    if not job_line:
                        job_line = stdout_line
                    else:
                        job_line = '\n'.join((job_line, stdout_line))
                    if 'job_username---' not in stdout_line:
                        continue
                    om_job = self.get_job_om(device,
                                             sqlserver,
                                             om_instance,
                                             owner_node,
                                             job_line)
                    if om_job:
                        jobs_oms.append(om_job)
                    job_line = ''
            if isCluster and version_index is not None:
                try:
                    om_instance.sql_server_version = stdout[version_index + 1].strip()
                except Exception:
                    log.debug('Version not found for om_instance %s', om_instance.id)

        maps['clear'] = eventmessage
        maps['databases'] = database_oms
        maps['instances'] = instance_oms
        maps['backups'] = backup_oms
        maps['jobs'] = jobs_oms
        maps['device'] = device_om
        maps['ao_info'] = ao_info

        defer.returnValue(maps)

    def get_db_om(self, om_instance, instance, owner_node, sqlserver, stdout_line):
        dbobj = stdout_line
        db = dbobj.split('\t')
        dbdict = {}

        for dbitem in db:
            try:
                key, value = dbitem.split('---')
                dbdict[key.lower()] = value.strip()
            except (ValueError):
                self.log.info('Error parsing returned values : {0}'.format(
                    dbitem))

        lastlogbackupdate = None
        if ('lastlogbackupdate' in dbdict) \
           and (dbdict['lastlogbackupdate'][:8] != '1/1/0001'):
            lastlogbackupdate = dbdict['lastlogbackupdate']

        lastbackupdate = None
        if ('lastbackupdate' in dbdict) \
           and (dbdict['lastbackupdate'][:8] != '1/1/0001'):
            lastbackupdate = dbdict['lastbackupdate']

        om_database = None
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
                owner_node, sqlserver)
            om_database.systemobject = dbdict['systemobject']
            om_database.recoverymodel = dbdict['recoverymodel']
        return om_database

    def get_backup_om(self, om_instance, instance, stdout_line):
        backupobj = stdout_line
        backup = backupobj.split('\t')
        backupdict = {}

        for backupitem in backup:
            key, value = backupitem.split('---')
            backupdict[key.lower()] = value.strip()

        if ('name' in backupdict):
            om_backup = ObjectMap()
            om_backup.id = self.prepId(instance + backupdict['name'])
            om_backup.title = backupdict['name']
            om_backup.devicetype = backupdict['devicetype']
            om_backup.physicallocation = backupdict['physicallocation']
            om_backup.status = backupdict['status']
            om_backup.instancename = om_instance.id
        return om_backup

    def get_job_om(self, device, sqlserver, om_instance, owner_node, stdout_line):
        jobobj = stdout_line
        # Make sure that the job description length does not go
        # beyond the buffer size (4096 characters).
        job_properties = (
            'job_username',
            'job_datecreated',
            'job_description',
            'job_jobid',
            'job_enabled',
            'job_jobname')
        jobdict = {}

        prev_index = len(jobobj)
        for prop in job_properties:
            start = jobobj.index(prop)
            jobitem = jobobj[start:prev_index]
            prev_index = start
            key, value = jobitem.split('---', 1)
            jobdict[key.lower()] = value.strip()

        om_job = ObjectMap()
        om_job.instancename = om_instance.id
        om_job.title = jobdict['job_jobname']
        om_job.cluster_node_server = '{0}//{1}'.format(
            owner_node, sqlserver)
        om_job.jobid = jobdict['job_jobid']
        om_job.id = self.prepId(om_job.jobid)
        om_job.enabled = 'Yes' if jobdict['job_enabled'] == 'True' else 'No'
        om_job.description = jobdict['job_description']
        om_job.datecreated = str(jobdict['job_datecreated'])
        om_job.username = jobdict['job_username']
        if not om_job.jobid:
            if not om_job.title:
                self.log.debug('Skipping job with no title or id on {}.'.format(device.id))
                return None
            om_job.jobid = self.prepId('sqljob_{}_{}'.format(om_job.instancename, om_job.title))
        return om_job

    def get_ao_sql_instance_oms(self, results):

        sql_instance_oms = []

        sql_instances = results.get('ao_info', {}).get('sql_instances', {})

        for sql_server_instance_full_name, ao_sql_instance in sql_instances.iteritems():

            instance_om = ObjectMap()

            is_clustered_instance = ao_sql_instance.get('is_clustered_instance', False)
            sql_instance_name = ao_sql_instance.get('instance_name')
            sql_instance_original_name = ao_sql_instance.get('instance_original_name')
            sql_hostname = ao_sql_instance.get('sqlhostname')
            sql_hostname_fqdn = ao_sql_instance.get('sql_hostname_fqdn')
            sql_host_ip = ao_sql_instance.get('sql_host_ip')
            # if there is no ip address for SQL Instance - try to take it from hosts info
            if not sql_host_ip and sql_hostname_fqdn:
                ip_and_hostname = self.get_ip_and_hostname(sql_hostname_fqdn)
                if isinstance(ip_and_hostname, list) and len(ip_and_hostname) == 2:
                    sql_host_ip = ip_and_hostname[0]
            sql_server_name = ao_sql_instance.get('sql_server_name')
            sql_server_version = ao_sql_instance.get('sql_server_version')

            sql_instance_id = get_ao_sql_instance_id(self.prepId, sql_instance_name,
                                                     is_clustered_instance, sql_hostname,
                                                     sql_server_instance_full_name)
            instance_om.id = sql_instance_id
            # Need to add non required properties only in case if they have value. Otherwise there is a
            # possibility of wiping existing values in case if SQL is unreachable.
            sql_instance_attrs = {}

            if sql_instance_original_name and sql_instance_name:
                if sql_instance_original_name == 'MSSQLSERVER':
                    sql_instance_attrs['perfmon_instance'] = 'SQLServer'
                    sql_instance_attrs['title'] = '{}(MSSQLSERVER)'.format(sql_instance_name)
                else:
                    sql_instance_attrs['perfmon_instance'] = 'MSSQL${}'.format(sql_instance_original_name)
                    sql_instance_attrs['title'] = sql_instance_name

            sql_instance_attrs['instancename'] = sql_instance_original_name
            sql_instance_attrs['sql_server_version'] = sql_server_version
            if sql_hostname_fqdn and sql_server_name:
                sql_instance_attrs['cluster_node_server'] = '{0}//{1}'.format(sql_hostname_fqdn, sql_server_name)
            sql_instance_attrs['owner_node_ip'] = sql_host_ip

            for attr_name, attr_value in sql_instance_attrs.iteritems():
                if attr_value:
                    setattr(instance_om, attr_name, attr_value)

            sql_instance_oms.append(instance_om)

        return sql_instance_oms

    def get_ao_oms(self, results, log):

        ag_relname = 'winsqlavailabilitygroups'
        ag_compname = 'os'
        ag_modname = 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityGroup'

        ar_relname = 'winsqlavailabilityreplicas'
        ar_compname = 'os/winsqlavailabilitygroups/{}'
        ar_modname = 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityReplica'

        al_relname = 'winsqlavailabilitylisteners'
        al_compname = 'os/winsqlavailabilitygroups/{}'
        al_modname = 'ZenPacks.zenoss.Microsoft.Windows.WinSQLAvailabilityListener'

        adb_relname = 'databases'
        adb_compname = 'os/winsqlinstances/{}'
        adb_modname = 'ZenPacks.zenoss.Microsoft.Windows.WinSQLDatabase'

        result = {
            'oms': [  # Add to list in order to preserve sequence of applying maps.
                defaultdict(list),  # Availability Groups
                defaultdict(list),  # Availability Replicas
                defaultdict(list),  # Availability Listeners
                defaultdict(list)  # Availability Databases
            ]
        }
        ag_result_index = 0
        ar_result_index = 1
        al_result_index = 2
        adb_result_index = 3

        # Add empty object map list for root ('os') containing relation for Availability Groups. This list will be
        # populated with actual maps below, but in case of result absence - we need to send empty maps to clean up
        # existing components.
        result['oms'][ag_result_index][(ag_relname, ag_compname, ag_modname)] = []

        sql_instances = results.get('ao_info', {}).get('sql_instances', {})

        # 1. Availability Groups
        availability_groups = results.get('ao_info', {}).get('availability_groups', {})
        for ag_id, ag_info in availability_groups.iteritems():
            ag_om = ObjectMap()
            # Get owner SQL Instance for 1:M relation
            owner_sql_instance_name = ag_info.get('primary_replica_server_name', '')
            if not owner_sql_instance_name:
                log.warn('Empty primary replica SQL Instance for Availability Group {}'.format(ag_id))
            owner_sql_instance_info = sql_instances.get(owner_sql_instance_name, {})

            sql_instance_data = {
                'sql_server_fullname': owner_sql_instance_info.get('sql_server_instance_full_name'),
                'sql_instance_name': owner_sql_instance_info.get('instance_name'),
                'is_clustered_instance': owner_sql_instance_info.get('is_clustered_instance'),
                'sql_hostname': owner_sql_instance_info.get('sqlhostname')
            }
            ag_om = fill_ag_om(ag_om, ag_info, self.prepId, sql_instance_data)
            result['oms'][ag_result_index][(ag_relname, ag_compname, ag_modname)].append(ag_om)

            # Add empty object maps list for Availability Group containing relations. Theses lists will be
            # populated with actual maps below, but in case of result absence - we need to send empty maps to clean up
            # existing Availability Group containing components (Availability Replicas, Availability Listeners).
            result['oms'][ar_result_index][(ar_relname,
                                            ar_compname.format(self.prepId(ag_id)),
                                            ar_modname)
                                           ] = []
            result['oms'][al_result_index][(al_relname,
                                           al_compname.format(self.prepId(ag_id)),
                                           al_modname)
                                           ] = []

        # 2. Availability Replicas
        availability_replicas = results.get('ao_info', {}).get('availability_replicas', {})
        # Also create SQL Instance & Availability Group to Replica mapping, to use it when determining Replica
        # for Databases
        ag_and_instance_to_replica_mapping = {}
        for ar_id, ar_info in availability_replicas.iteritems():
            # Get Availability Group for containing relation
            owner_ag_id = ar_info.get('ag_res_id', '')
            if not owner_ag_id or owner_ag_id not in availability_groups:
                log.warn('Empty owner Availability Group for Availability Replica {}. Skipping.'.format(ar_id))
                continue
            ar_om = ObjectMap()
            # Get owner SQL Instance for 1:M relation
            owner_sql_instance_name = ar_info.get('replica_server_name', '')
            if not owner_sql_instance_name:
                log.warn('Empty owner SQL Instance for Availability Replica {}'.format(ar_id))
            owner_sql_instance_info = sql_instances.get(owner_sql_instance_name, {})

            ag_and_instance_to_replica_mapping[(owner_ag_id,
                                                owner_sql_instance_info.get('sql_server_instance_full_name'))] = ar_id
            sql_instance_data = {
                'sql_server_fullname': owner_sql_instance_info.get('sql_server_instance_full_name'),
                'sql_instance_name': owner_sql_instance_info.get('instance_name'),
                'is_clustered_instance': owner_sql_instance_info.get('is_clustered_instance'),
                'sql_hostname': owner_sql_instance_info.get('sqlhostname'),
            }
            ar_om = fill_ar_om(ar_om, ar_info, self.prepId, sql_instance_data)
            result['oms'][ar_result_index][(ar_relname,
                                           ar_compname.format(self.prepId(owner_ag_id)),
                                           ar_modname)
                                           ].append(ar_om)

        # 3. Availability Listeners
        availability_listeners = results.get('ao_info', {}).get('availability_listeners', {})
        for al_id, al_info in availability_listeners.iteritems():
            # Get Availability Group for containing relation
            owner_ag_id = al_info.get('ag_id', '')
            if not owner_ag_id or owner_ag_id not in availability_groups:
                log.warn('Empty owner Availability Group for Availability Listener {}. Skipping.'.format(al_id))
                continue
            al_om = ObjectMap()
            al_om = fill_al_om(al_om, al_info, self.prepId)
            result['oms'][al_result_index][(al_relname,
                                           al_compname.format(self.prepId(owner_ag_id)),
                                           al_modname)
                                           ].append(al_om)

        # Add empty object maps list for Always On SQL Instance contained relations. This lists will be
        # populated with actual maps below, but in case of result absence - we need to send empty maps to clean up
        # existing Always On SQL Instance contained components (Availability Databases).
        for sql_server_instance_full_name in sql_instances.iterkeys():
            result['oms'][adb_result_index][(adb_relname,
                                             adb_compname.format(self.prepId(sql_server_instance_full_name)),
                                             adb_modname)
                                            ] = []

        # 4. Availability Databases
        availability_databases = results.get('ao_info', {}).get('availability_databases', {})
        for adb_id_tuple, adb_info in availability_databases.iteritems():
            # Get SQL Instance for containing relation
            adb_owner_id, adb_index = adb_id_tuple
            if not adb_owner_id or adb_owner_id not in sql_instances:
                log.warn('Empty owner SQL instance for Availability Database {}. Skipping.'.format(adb_info.get('name'),
                                                                                                   adb_index))
                continue

            # add owner SQL Instance related data to databases info dict
            adb_info['adb_owner_id'] = adb_owner_id
            adb_info['sql_hostname_fqdn'] = sql_instances[adb_owner_id].get('sql_hostname_fqdn')
            adb_info['sql_server_name'] = sql_instances[adb_owner_id].get('sql_server_name')
            adb_info['instancename'] = sql_instances[adb_owner_id].get('instance_original_name')

            # Determine Availability Replica to which database belongs
            db_replica_id = ag_and_instance_to_replica_mapping.get(
                (adb_info.get('ag_res_id'), adb_owner_id)
            )
            if db_replica_id:
                adb_info['db_replica_id'] = db_replica_id

            adb_om = ObjectMap()
            adb_om = fill_adb_om(adb_om, adb_info, self.prepId)
            result['oms'][adb_result_index][(adb_relname,
                                             adb_compname.format(self.prepId(adb_owner_id)),
                                             adb_modname)
                                            ].append(adb_om)

        return result

    @save
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

        # Always On SQL Instances oms
        ao_sql_instances_oms = self.get_ao_sql_instance_oms(results)

        maps.append(RelationshipMap(
            relname="winsqlinstances",
            compname="os",
            modname="ZenPacks.zenoss.Microsoft.Windows.WinSQLInstance",
            objmaps=results['instances'] + ao_sql_instances_oms  # add AO SQL Instances oms (do not extend existed list
            # as we operate with AO SQL Instance's databases separately)
        ))

        # send empty oms if no jobs, dbs, backups for an instance
        for instance in results['instances']:
            if instance.id not in map_backups_instance_oms:
                map_backups_instance_oms[instance.id] = []
            if instance.id not in map_jobs_instance_oms:
                map_jobs_instance_oms[instance.id] = []
            if instance.id not in map_dbs_instance_oms:
                map_dbs_instance_oms[instance.id] = []

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

        # Always On components Object maps
        ao_oms = self.get_ao_oms(results, log)
        ao_oms = ao_oms.get('oms', [])
        log.debug('Always On components Object maps: {}'.format(ao_oms))
        for map_category in ao_oms:
            for key, oms in map_category.iteritems():
                relname, compname, modname = key
                maps.append(RelationshipMap(
                    relname=relname,
                    compname=compname,
                    modname=modname,
                    objmaps=oms))

        try:
            for instance, errors in results['errors'].items():
                if errors:
                    msg = '{}: {}'.format(instance, sanitize_error(errors))
                    self._send_event(msg, device.id, 3, summary='Unsuccessful SQL Server collection')
                else:
                    msg = 'Successful collection for {}'.format(instance)
                    self._send_event(msg, device.id, 0, summary='Successful SQL Server collection')
        except KeyError:
            # This is for unit tests to pass, no need to try and send events
            pass
        return maps


def sanitize_error(error):
    fullerror = '\n'.join(error)
    try:
        fullerror = fullerror[:fullerror.index('At line:') - 1]
    except ValueError:
        pass
    if 'Failed to connect to server' in fullerror:
        fullerror += ' Is SQL Server online?  Are your credentials correct?'
        fullerror += ' Do you have "View server state" permissions?'
    return fullerror


def check_username(databases, instance, log):
    stderr = ''.join(databases.stderr)
    stdout = ' '.join(databases.stdout)
    if (('Exception calling "Connect" with "0" argument(s): '
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
    if databases.stdout and 'assembly load error' in stdout:
        log.error('SQL Server Management Object Assemblies were not found on the server. '
                  'Please be sure they are installed.')
