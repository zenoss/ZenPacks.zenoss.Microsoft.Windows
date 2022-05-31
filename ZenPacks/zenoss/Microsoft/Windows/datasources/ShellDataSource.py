##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses WinRS to run remote commands.

See Products.ZenModel.ZenPack._getClassesByPath() to understand how this class
gets discovered as a datasource type in Zenoss.
"""

import time
import logging
import urllib
from urlparse import urlparse
from traceback import format_exc
import re

from zope.component import adapts
from zope.component import getGlobalSiteManager
from zope.component import queryUtility
from zope.interface import implements
from zope.interface import Interface

from twisted.internet import defer
from twisted.python.failure import Failure
from Products.DataCollector.plugins.DataMaps import ObjectMap
from Products.DataCollector.Plugins import getParserLoader, loadParserPlugins
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.interfaces import IRRDDataSourceInfo
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.Zuul.utils import safe_hasattr
from Products.Zuul.infos.template import RRDDataSourceInfo
from Products.ZenUtils.Utils import prepId
from Products.ZenEvents import ZenEventClasses
from Products.ZenRRD.CommandParser import ParsedResults
from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin

from ..txcoroutine import coroutine

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
from ZenPacks.zenoss.Microsoft.Windows.utils import filter_sql_stdout, \
    parseDBUserNamePass, getSQLAssembly, parse_winrs_response
from ..utils import (
    check_for_network_error, save, errorMsgCheck,
    generateClearAuthEvents, get_dsconf, SqlConnection,
    lookup_databasesummary, lookup_database_status,
    lookup_ag_state, lookup_ag_quorum_state, fill_ag_om, fill_ar_om, fill_al_om, fill_adb_om,
    get_default_properties_value_for_component, get_prop_value_events, get_db_om, get_db_monitored)
from EventLogDataSource import string_to_lines
from . import send_to_debug


# Requires that txwinrm_utils is already imported.
from txwinrm.util import RequestError
from txwinrm.WinRMClient import SingleCommandClient


log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
WINRS_SOURCETYPE = 'Windows Shell'
AVAILABLE_STRATEGIES = [
    'Custom Command',
    'powershell MSSQL',
    'DCDiag',
    'powershell MSSQL Instance',
    'powershell MSSQL Job',
    'powershell MSSQL AO AG',
    'powershell MSSQL AO AR',
    'powershell AO AL',
    'powershell MSSQL AO ADB'
]

BUFFER_SIZE = '$Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size (4096, 512);'

gsm = getGlobalSiteManager()


class WindowsShellException(Exception):
    '''Exception class to catch known exceptions '''


class ShellResult(object):
    exit_code = 0
    stderr = []
    stdout = []


class ShellDataSource(PythonDataSource):
    """
    Subclass PythonDataSource to put a new datasources into Zenoss
    """

    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = 300
    resource = ''
    strategy = ''
    parser = ''
    usePowershell = True
    script = ''

    _properties = PythonDataSource._properties + (
        {'id': 'resource', 'type': 'string'},
        {'id': 'strategy', 'type': 'string'},
        {'id': 'parser', 'type': 'string'},
        {'id': 'usePowershell', 'type': 'boolean'},
        {'id': 'script', 'type': 'string'}
    )
    sourcetypes = (WINRS_SOURCETYPE,)
    sourcetype = sourcetypes[0]
    plugin_classname = ZENPACKID + \
        '.datasources.ShellDataSource.ShellDataSourcePlugin'


class IShellDataSourceInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the Shell datasource.
    """

    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    strategy = schema.TextLine(
        group=_t(WINRS_SOURCETYPE),
        title=_t('Strategy'),
        xtype='winrsstrategy')


class ShellDataSourceInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the Shell plugin.
    """
    implements(IShellDataSourceInfo)
    adapts(ShellDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    resource = ProxyProperty('resource')
    strategy = ProxyProperty('strategy')
    parser = ProxyProperty('parser')
    usePowershell = ProxyProperty('usePowershell')
    script = ProxyProperty('script')

    @property
    def availableParsers(self):
        """
        returns a list of all available parsers
        """
        return sorted(p.modPath for p in loadParserPlugins(self._object.dmd))

    @property
    def availableStrategies(self):
        """
        returns a list of available winrs strategies
        """
        return sorted(AVAILABLE_STRATEGIES)


class ParsedResults(ParsedResults):
    """
    Shell version of ParsedResults. Includes the 'maps' list to automatically apply
    modeling maps.
    """
    def __init__(self):
        self.maps = []
        super(ParsedResults, self).__init__()


class CmdResult(object):
    """
    Emulate the ZenCommand result object for WinCmd
    """
    output = ''
    exitCode = None


class WinCmd(object):
    """
    Emulate the SSH/ZenCommand returned object (Products.ZenRRD.zencommand.Cmd) for
    compatibility with existing Command parsers
    """
    name = None
    device = ''
    command = None
    component = ''
    ds = ''
    useSsh = False
    cycleTime = None
    env = None
    eventClass = None
    eventKey = None
    lastStart = 0
    lastStop = 0
    points = None
    result = CmdResult()
    severity = 3
    usePowershell = False
    deviceConfig = None

    def __init__(self):
        self.points = []

    def setDatasource(self, datasource):
        self.datasource = datasource


class IStrategy(Interface):
    ''' Interface for strategy '''


class DCDiagStrategy(object):
    implements(IStrategy)

    key = 'DCDiag'

    def build_command_line(self, tests, testparms, username, password):
        self.run_tests = set(tests)
        user_parts = username.split('@')
        domain = user_parts[1] if len(user_parts) > 1 else ''
        dcuser = '{}\\{}'.format(domain.split('.')[0], user_parts[0])
        dcdiagcommand = 'dcdiag /q /u:{} /p:{} /test:'.format(dcuser, password) + ' /test:'.join(tests)
        if testparms:
            dcdiagcommand += ' ' + ' '.join(testparms)
        return dcdiagcommand

    def parse_result(self, config, result):
        log.debug('DCDiag error on {}: {}'.format(config.id, '\n'.join(result.stderr)))
        log.debug('DCDiag results on {}: {}'.format(config.id, '\n'.join(result.stdout)))

        def get_datasource(test_name):
            for ds in config.datasources:
                if ds.params['resource'] == test_name:
                    return ds
        # ZPS-1146: Correctly join output to avoid situations when test name
        # jumps to next line:
        # ......................... <COMP-NAME> failed test\n<TEST-NAME>
        output = self._clean_output(result.stdout)
        collectedResults = ParsedResults()
        tests_in_error = set()
        if output:
            error_str = ''
            for line in output:
                # Failure of a test shows the error message first followed by:
                # "......................... <dc> failed test <testname>"
                if line.startswith('........'):
                    # create err event
                    match = re.match('.*test (.*)', line)
                    if not match:
                        test = 'Unknown'
                    else:
                        test = match.group(1)
                        tests_in_error.add(test)
                    if not error_str:
                        error_str = 'Unknown'
                    msg = "'DCDiag /test:{}' failed: {}".format(test, error_str)
                    eventkey = 'WindowsActiveDirectory{}'.format(test)

                    dsconf = get_datasource(test)
                    # default to first ds
                    if not dsconf:
                        dsconf = config.datasources[0]
                    eventClass = dsconf.eventClass if dsconf.eventClass else "/Status"

                    collectedResults.events.append({
                        'eventClass': eventClass,
                        'severity': dsconf.severity,
                        'eventClassKey': 'WindowsActiveDirectoryStatus',
                        'eventKey': eventkey,
                        'summary': msg.split('.')[0],
                        'message': msg,
                        'device': config.id})
                    error_str = ''
                else:
                    error_str += line if not error_str else ' ' + line
        for diag_test in self.run_tests.difference(tests_in_error):
            # Clear events
            msg = "'DCDiag /test:{}' passed".format(diag_test)
            eventkey = 'WindowsActiveDirectory{}'.format(diag_test)

            dsconf = get_datasource(diag_test)
            # default to first ds
            if not dsconf:
                dsconf = config.datasources[0]
            eventClass = dsconf.eventClass if dsconf.eventClass else "/Status"
            collectedResults.events.append({
                'eventClass': eventClass,
                'severity': ZenEventClasses.Clear,
                'eventClassKey': 'WindowsActiveDirectoryStatus',
                'eventKey': eventkey,
                'summary': msg.split('.')[0],
                'message': msg,
                'device': config.id})
        return collectedResults

    def _clean_output(self, output):
        if len(output) == 0:
            return output

        cleaned_lines = [output[0]]

        for ln in output[1:]:
            last_ln = cleaned_lines[-1]
            joined_ln = '{} {}'.format(last_ln, ln)

            # join last line with the current one in case if it contains
            # "failed test <test-name>" where <test-name> is one of the run
            # tests.
            # BUT don't join them if current line also starts with dots (that's
            # going to be another test result)
            if last_ln.startswith('........') and not ln.startswith('........')\
                    and any('failed test {}'.format(test) in joined_ln
                            for test in self.run_tests)\
                    and any(test in ln for test in self.run_tests):
                cleaned_lines[-1] = joined_ln
            else:
                cleaned_lines.append(ln)
        return cleaned_lines


gsm.registerUtility(DCDiagStrategy(), IStrategy, 'DCDiag')


class CustomCommandStrategy(object):
    implements(IStrategy)

    key = 'CustomCommand'

    def build_command_line(self, script, usePowershell):
        if not usePowershell:
            return script, None
        script = script.replace('"', r'\"')
        pscommand = 'powershell -NoLogo -NonInteractive -NoProfile -OutputFormat TEXT ' \
                    '-Command'
        return pscommand, '"{}{}"'.format(BUFFER_SIZE, script)

    def parse_result(self, config, result):
        dsconf = config.datasources[0]
        parserLoader = dsconf.params['parser']
        log.debug('{}: Trying to use the {} parser'.format(config.id, parserLoader.pluginName))

        # Build emulated Zencommand Cmd object
        cmd = WinCmd()
        cmd.setDatasource(dsconf)
        cmd.name = '{}/{}'.format(dsconf.template, dsconf.datasource)
        cmd.command = dsconf.params['script']

        cmd.ds = dsconf.datasource
        cmd.device = dsconf.params['servername']
        if dsconf.component is not None and len(dsconf.component):
            cmd.component = dsconf.component
        else:
            cmd.component = dsconf.params['contextcompname']

        # Pass the severity from the datasource to the command parsers
        # If Nagios, check the status for severity
        cmd.result.output = '\n'.join(result.stdout)
        if parserLoader.pluginName in ('Nagios', 'Auto'):
            try:
                status, data = cmd.result.output.split('|', 1)
                if 'OK' in status:
                    severity = ZenEventClasses.Clear
                elif 'WARNING' in status:
                    severity = ZenEventClasses.Warning
                elif 'CRITICAL' in status:
                    severity = ZenEventClasses.Critical
                else:
                    severity = dsconf.severity
            except Exception:
                severity = dsconf.severity
        else:
            severity = dsconf.severity
        cmd.severity = severity
        eventClass = dsconf.eventClass if dsconf.eventClass else "/Status"
        cmd.eventClass = eventClass
        cmd.eventKey = dsconf.eventKey

        # Add the device id to the config for compatibility with parsers
        config.device = config.id
        cmd.deviceConfig = config
        cmd.deviceConfig.name = config.id

        # Add the component id to the points array for compatibility with parsers
        for point in dsconf.points:
            point.component = cmd.component
            cmd.points.append(point)

        cmd.usePowershell = dsconf.params['usePowershell']
        cmd.result.exitCode = result.exit_code

        collectedResult = ParsedResults()
        parser = parserLoader.create()
        parser.processResults(cmd, collectedResult)
        # Give error feedback to user
        if result.stderr:
            errors = '\n'.join(result.stderr)
            log.debug('Custom command errors on {}: {}'.format(config.id, errors))
            try:
                err_index = [i for i, val in enumerate(result.stderr) if "At line:" in val][0]
                msg = 'Custom Command error: ' + ''.join(result.stderr[:err_index])
            except Exception:
                msg = 'Custom Command error: ' + ''.join(result.stderr)
            collectedResult.events.append({
                'eventClass': eventClass,
                'severity': dsconf.severity or ZenEventClasses.Warning,
                'eventClassKey': 'WindowsCommandCollectionError',
                'eventKey': 'WindowsCommandCollection',
                'summary': msg,
                'device': config.id})
        else:
            log.debug('Custom command results on {}: {}'.format(config.id, cmd.result.output))
            msg = 'Custom Command success'
            collectedResult.events.append({
                'eventClass': eventClass,
                'severity': ZenEventClasses.Clear,
                'eventClassKey': 'WindowsCommandCollectionError',
                'eventKey': 'WindowsCommandCollection',
                'summary': msg,
                'device': config.id})
        return collectedResult


gsm.registerUtility(CustomCommandStrategy(), IStrategy, 'Custom Command')


class PowershellMSSQLStrategy(object):
    implements(IStrategy)

    key = 'PowershellMSSQL'

    def build_command_line(self, sqlConnection):
        pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

        # We should not be running this per database.  Bad performance problems when there are
        # a lot of databases.  Run script per instance

        counters_sqlConnection = []
        # smo optimization for faster loading
        counters_sqlConnection.append("$ob = New-Object Microsoft.SqlServer.Management.Smo.Database;"
                                      "$def = $server.GetDefaultInitFields($ob.GetType());"
                                      "$server.SetDefaultInitFields($ob.GetType(), $def);")
        counters_sqlConnection.append("$ob = New-Object Microsoft.SqlServer.Management.Smo.Table;"
                                      "$def = $server.GetDefaultInitFields($ob.GetType());"
                                      "$server.SetDefaultInitFields($ob.GetType(), $def);")
        counters_sqlConnection.append("if ($server.Databases -ne $null) {")
        counters_sqlConnection.append("$dbMaster = $server.Databases['master'];")
        counters_sqlConnection.append("foreach ($db in $server.Databases){")
        counters_sqlConnection.append("$db_name = '';"
                                      "$sp = $db.Name.split($([char]39)); "
                                      "if($sp.length -ge 2){ "
                                      "foreach($i in $sp){ "
                                      "if($i -ne $sp[-1]){ $db_name += $i + [char]39 + [char]39;}"
                                      "else { $db_name += $i;}"
                                      "}} else { $db_name = $db.Name;}"
                                      "Write-Host '{{db_name}} :counter: databasestatus :value: {{status}}'.replace"
                                      "('{{db_name}}', $db_name).replace('{{status}}', $db.Status);}")
        counters_sqlConnection.append("$query = 'select RTRIM(instance_name), "
                                      "RTRIM(counter_name), RTRIM(cntr_value) from "
                                      "sys.dm_os_performance_counters where instance_name in "
                                      "(select name from sys.databases)';")
        counters_sqlConnection.append("$ds = $dbMaster.ExecuteWithResults($query);")
        counters_sqlConnection.append("if($ds.Tables[0].rows.count -gt 0) {$ds.Tables[0].rows"
                                      "| % {write-host $_.Column1':counter:'$_.Column2':value:'$_.Column3;} } }")
        script = "\"& {{{}}}\"".format(
            ''.join([BUFFER_SIZE] +
                    getSQLAssembly(sqlConnection.version) +
                    sqlConnection.sqlConnection +
                    counters_sqlConnection))
        return pscommand, script

    def parse_result(self, dsconfs, result):
        if result.stderr:
            log.debug('MSSQL error: {0}'.format('\n'.join(result.stderr)))
        log.debug('MSSQL results: {}'.format('\n'.join(result.stdout)))

        if result.exit_code != 0:
            for dsconf in dsconfs:
                dsconf.params['counter'] = dsconf
            counters = dsconf.params['counter']
            log.debug(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return

        # Parse values
        self.valuemap = {}
        db_regex = re.compile('(.*):counter:(.*):value:(.*)')
        for counterline in filter_sql_stdout(result.stdout):
            try:
                databasename, _counter, value = db_regex.match(counterline).groups()
                databasename = databasename.strip()
                _counter = _counter.strip().lower()
                value = value.strip()
            except Exception:
                log.debug('MSSQL parse_result error in data: %s', counterline)
                continue
            if databasename not in self.valuemap:
                self.valuemap[databasename] = {}
            if _counter == 'databasestatus':
                self.valuemap[databasename]['status'] = value
            else:
                self.valuemap[databasename][_counter] = value

        for dsconf in dsconfs:
            timestamp = int(time.mktime(time.localtime()))
            if dsconf.params['resource'] == 'status':
                # no need to get status as it's handled differently
                yield dsconf, '', timestamp
                continue
            databasename = dsconf.params['contexttitle']
            try:
                key = dsconf.params['resource'].lower()
                value = float(self.valuemap[databasename][key])
                yield dsconf, value, timestamp
            except Exception:
                log.debug("No value was returned for counter {0} on {1}".format(dsconf.params['resource'], databasename))


gsm.registerUtility(PowershellMSSQLStrategy(), IStrategy, 'powershell MSSQL')


class PowershellMSSQLJobStrategy(object):
    implements(IStrategy)

    key = 'MSSQLJob'

    def build_command_line(self, sqlConnection):
        pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

        jobs_sqlConnection = []
        jobs_sqlConnection.append("if ($server.JobServer -ne $null) {")
        jobs_sqlConnection.append("foreach ($job in $server.JobServer.Jobs) {")
        jobs_sqlConnection.append("write-host 'job:'$job.Name")
        jobs_sqlConnection.append("'|IsEnabled:'$job.IsEnabled")
        jobs_sqlConnection.append("'|LastRunDate:'$job.LastRunDate")
        jobs_sqlConnection.append("'|LastRunOutcome:'$job.LastRunOutcome")
        jobs_sqlConnection.append("'|CurrentRunStatus:'$job.CurrentRunStatus;")
        jobs_sqlConnection.append("}}")
        script = "\"& {{{}}}\"".format(
            ''.join([BUFFER_SIZE] +
                    getSQLAssembly(sqlConnection.version) +
                    sqlConnection.sqlConnection +
                    jobs_sqlConnection))
        return pscommand, script

    def parse_result(self, dsconfs, result):
        log.debug('MSSQLJob results: {}'.format(result))
        collectedResults = ParsedResults()
        if result.stderr:
            log.debug('MSSQL error: {0}' + ''.join(result.stderr))

        if result.exit_code != 0:
            log.info(
                'Non-zero exit code ({}) for job query status on {}'
                .format(
                    result.exit_code, dsconfs[0].device))
            return collectedResults

        # Parse values
        valuemap = {}
        jobname = 'Unknown'
        try:
            for jobline in filter_sql_stdout(result.stdout):
                for job in jobline.split('|'):
                    key, value = job.split(':', 1)
                    if key.strip() == 'job':
                        jobname = value.strip()
                        if jobname not in valuemap:
                            valuemap[jobname] = {}
                    else:
                        valuemap[jobname][key] = value.strip()
        except ValueError:
            msg = 'Malformed data received for MSSQL Job {}'.format(jobname)
            collectedResults.events.append({
                'severity': ZenEventClasses.Error,
                'eventClassKey': 'winrsCollection MSSQLJob',
                'eventKey': dsconfs[0].eventKey if dsconfs[0].eventKey else self.key,
                'summary': msg,
                'device': dsconfs[0].device,
                'query_results': result.stdout
            })

        for dsconf in dsconfs:
            component = dsconf.params['contexttitle']
            eventClass = dsconf.eventClass if dsconf.eventClass else "/Status"
            try:
                currentstate = {
                    'Succeeded': ZenEventClasses.Clear,
                    'Failed': dsconf.severity
                }.get(valuemap[component]['LastRunOutcome'], ZenEventClasses.Info)
                msg = 'LastRunOutcome for job "{}": {} at {}'.format(
                    component,
                    valuemap[component]['LastRunOutcome'],
                    valuemap[component]['LastRunDate'])
                collectedResults.events.append({
                    'eventClass': eventClass,
                    'severity': currentstate,
                    'eventClassKey': 'winrsCollection MSSQLJob',
                    'eventKey': dsconf.eventKey if dsconf.eventKey else self.key,
                    'summary': msg,
                    'device': dsconf.device,
                    'component': dsconf.component})
                collectedResults.events.append({
                    'severity': ZenEventClasses.Clear,
                    'eventClassKey': 'winrsCollectionMSSQLJob',
                    'eventKey': dsconf.eventKey if dsconf.eventKey else self.key,
                    'summary': 'Successful MSSQL Job collection',
                    'device': dsconf.device,
                    'component': dsconf.component})
            except Exception:
                msg = 'Missing or no data returned when querying job "{}"'.format(component)
                collectedResults.events.append({
                    'severity': dsconf.severity,
                    'eventClassKey': 'winrsCollectionMSSQLJob',
                    'eventKey': dsconf.eventKey if dsconf.eventKey else self.key,
                    'summary': msg,
                    'device': dsconf.device,
                    'component': dsconf.component
                })
        return collectedResults


gsm.registerUtility(PowershellMSSQLJobStrategy(), IStrategy, 'powershell MSSQL Job')


class PowershellMSSQLInstanceStrategy(object):
    implements(IStrategy)

    key = 'MSSQLInstance'

    def build_command_line(self, instance):
        pscommand = "powershell -NoLogo -NonInteractive " \
            "-OutputFormat TEXT -Command "

        psInstanceCommands = []
        psInstanceCommands.append(BUFFER_SIZE)
        psInstanceCommands.append("$inst = Get-Service -DisplayName 'SQL Server ({0})';".format(instance))
        psInstanceCommands.append("Write-Host $inst.Status'|'$inst.Name;")

        script = "\"& {{{}}}\"".format(
            ''.join(psInstanceCommands))
        return pscommand, script

    def parse_result(self, dsconfs, result):
        if result.exit_code != 0:
            counters = [dsconf.params['resource'] for dsconf in dsconfs]
            log.info(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return

        # Parse values
        stdout = parse_stdout(result)
        if stdout:
            status, name = stdout
            dsconf0 = dsconfs[0]

            compObject = ObjectMap()
            compObject.id = dsconf0.params['instanceid']
            compObject.title = dsconf0.params['instancename']
            compObject.compname = dsconf0.params['contextcompname']
            compObject.modname = dsconf0.params['contextmodname']
            compObject.relname = dsconf0.params['contextrelname']

            for dsconf in dsconfs:
                value = (
                    dsconf0.params['instanceid'],
                    status.strip(),
                    compObject
                )
                yield dsconf, value
        else:
            log.debug('Error in parsing mssql instance data')


gsm.registerUtility(PowershellMSSQLInstanceStrategy(), IStrategy, 'powershell MSSQL Instance')


class PowershellMSSQLAlwaysOnAGStrategy(object):
    implements(IStrategy)

    key = 'MSSQLAlwaysOnAG'

    @staticmethod
    def build_command_line(sql_connection, ag_names):
        ps_command = "powershell -NoLogo -NonInteractive " \
            "-OutputFormat TEXT -Command "

        ps_ao_ag_script = \
            ("$res = New-Object 'system.collections.generic.dictionary[string, object]';"

             "$def_fields = $server.GetDefaultInitFields([Microsoft.SqlServer.Management.Smo.AvailabilityGroup]);"
             "$server.SetDefaultInitFields([Microsoft.SqlServer.Management.Smo.AvailabilityGroup], $def_fields);"
             "$dbmaster = $server.Databases['master'];"
             "$is_clustered = $server.IsClustered;"

             '$cluster_query = \\"SELECT quorum_state FROM sys.dm_hadr_cluster;\\";'
             "   try {"
             "       $cl_qry_res = $dbmaster.ExecuteWithResults($cluster_query);"
             "       if ($cl_qry_res.tables[0].rows.Count -gt 0) {"
             "          $cl_quorum_state = $cl_qry_res.tables[0].rows[0].quorum_state;"
             "       } else {$cl_quorum_state = '';}"
             "   }"
             "   catch {"
             "       $cl_quorum_state = '';"
             "   }"
             "$ag_names = @(ag_names_placeholder);"
             "foreach ($ag_name in $ag_names) {"
             "   $ag = New-Object 'Microsoft.SqlServer.Management.Smo.AvailabilityGroup' $server, $ag_name;"

             "   $ag.Refresh();"
             "   $ag_result = New-Object 'system.collections.generic.dictionary[string, object]';"
             ""
             "   $ag_info = New-Object 'system.collections.generic.dictionary[string, object]';"
             "   $ag_info['primary_replica_server_name'] = $ag.PrimaryReplicaServerName;"
             "   $ag_info['health_check_timeout'] = $ag.HealthCheckTimeout;"
             "   $ag_info['automated_backup_preference'] = $ag.AutomatedBackupPreference;"
             "   $ag_info['is_clustered_instance'] = $is_clustered;"
             "   $ag_uid = $ag.UniqueId;"
             '   $ag_health_query = \\"SELECT ag_states.synchronization_health AS synchronization_health, '
             "   ag_states.primary_recovery_health AS primary_recovery_health"
             "   FROM sys.dm_hadr_availability_group_states AS ag_states"
             '   WHERE ag_states.group_id = \'$ag_uid\';\\";'
             "   try {"
             "       $ag_st_res = $dbmaster.ExecuteWithResults($ag_health_query);"
             "       $ag_info['synchronization_health'] = $ag_st_res.tables[0].rows[0].synchronization_health;"
             "       $ag_info['primary_recovery_health'] = $ag_st_res.tables[0].rows[0].primary_recovery_health;"
             "   }"
             "   catch {"
             "       $ag_info['synchronization_health'] = '';"
             "       $ag_info['primary_recovery_health'] = '';"
             "   }"
             "   $ag_result['ag_info'] = $ag_info;"
             ""
             "   $ag_state = New-Object 'Microsoft.SqlServer.Management.Smo.AvailabilityGroupState' $ag;"
             "   $ag_result['ag_state'] = $ag_state;"
             "   $ag_result['cl_quorum_state'] = $cl_quorum_state;"
             ""
             "   $res[$ag_name] = $ag_result;"
             "}"
             "$result_in_json = ConvertTo-Json $res;"
             "Write-Host $result_in_json;").replace('ag_names_placeholder',
                                                    ','.join(("'{}'".format(ag_name) for ag_name in ag_names)))
        script = "\"& {{{}}}\"".format(
            ''.join([BUFFER_SIZE] +
                    getSQLAssembly(sql_connection.version) +
                    sql_connection.sqlConnection +
                    [ps_ao_ag_script]))

        log.debug('Powershell MSSQL Always On AG Strategy script: {}'.format(script))

        return ps_command, script

    @staticmethod
    def parse_result(config, result):

        datasources = config.datasources

        parsed_results = PythonDataSourcePlugin.new_data()

        if result.stderr:
            log.debug('MSSQL AO AG error: {0}'.format('\n'.join(result.stderr)))
        log.debug('MSSQL AO AG results: {}'.format('\n'.join(result.stdout)))

        if result.exit_code != 0:
            log.debug(
                'Non-zero exit code ({0}) for MSSQL AO AG on {1}'
                .format(
                    result.exit_code, datasources[0].cluster_node_server))
            return parsed_results

        # Parse values
        ag_info_stdout = filter_sql_stdout(result.stdout)
        availability_groups_info, passing_error = parse_winrs_response(ag_info_stdout, 'json')

        if not availability_groups_info and passing_error:
            log.debug('Error during parsing Availability Groups State counters')
            return parsed_results

        log.debug('Availability Groups monitoring response: {}'.format(availability_groups_info))

        if not availability_groups_info:
            log.debug('Got empty Availability group response for {}'.format(datasources[0].cluster_node_server))
            availability_groups_info = {}  # need for further setting of default values.

        for dsconf in datasources:
            ag_name = dsconf.params.get('contexttitle', '')
            ag_results = availability_groups_info.get(ag_name, {})

            # Metrics
            ag_state_metrics = ag_results.get('ag_state')
            if isinstance(ag_state_metrics, dict):
                if dsconf.datasource == 'AvailabilityGroupState':
                    for datapoint in dsconf.points:
                        dp_id = datapoint.id
                        dp_value = ag_state_metrics.get(dp_id)
                        if dp_value is not None:
                            parsed_results['values'][dsconf.component][dp_id] = dp_value, 'N'
            # Maps:
            ag_info_maps = ag_results.get('ag_info')
            if not ag_info_maps:
                log.debug('Got empty maps response for Availability Group {}.'.format(ag_name))
                # We got empty result for particular Availability Group - seems like it is unreachable.
                # Need to return set of properties with default values
                ag_info_maps = get_default_properties_value_for_component('WinSQLAvailabilityGroup')

            ag_om = ObjectMap()
            ag_om.id = dsconf.params['instanceid']
            ag_om.title = dsconf.params['contexttitle']
            ag_om.compname = dsconf.params['contextcompname']
            ag_om.modname = dsconf.params['contextmodname']
            ag_om.relname = dsconf.params['contextrelname']
            sql_instance_data = {
                'quorum_state': lookup_ag_quorum_state(
                    ag_results.get('cl_quorum_state'))
            }
            ag_om = fill_ag_om(ag_om, ag_info_maps, prepId, sql_instance_data)
            parsed_results['maps'].append(ag_om)

            # Events:
            # 1. check whether Primary replica SQL Instance has changed. If yes - create an event.
            primary_repliaca_sql_instance_id = getattr(ag_om, 'set_winsqlinstance', None)
            if primary_repliaca_sql_instance_id and \
                    dsconf.params['winsqlinstance_id'] and \
                    primary_repliaca_sql_instance_id != dsconf.params['winsqlinstance_id']:

                parsed_results['events'].append(dict(
                    eventClassKey='alwaysOnPrimaryReplicaInstanceChange',
                    eventKey='winrsCollection',
                    severity=ZenEventClasses.Info,
                    summary='Primary replica SQL Instance for Availability Group {} changed to {}'.format(
                                dsconf.params['contexttitle'],
                                ag_info_maps.get('primary_replica_server_name'), ''),
                    device=config.id,
                    component=dsconf.component
                ))
            # 2. IsOnline event
            is_online = None
            if isinstance(ag_state_metrics, dict):
                is_online = ag_state_metrics.get('IsOnline')
                try:
                    is_online = int(is_online)
                except TypeError:
                    pass
            state_representation = lookup_ag_state(is_online)
            severity = ZenEventClasses.Clear if is_online else ZenEventClasses.Critical

            parsed_results['events'].append(dict(
                eventClass=dsconf.eventClass or "/Status",
                eventClassKey='alwaysOnAvailabilityGroupStatus',
                eventKey=dsconf.eventKey,
                severity=severity,
                summary='Last state of Availability Group {} was {}'.format(
                    dsconf.params['contexttitle'], state_representation),
                device=config.id,
                component=dsconf.component
            ))
            # 3. Events based on Availability Group properties values
            ag_prop_value_events = get_prop_value_events(
                'WinSQLAvailabilityGroup',
                ag_om.__dict__,
                dict(
                    event_class=dsconf.eventClass or "/Status",
                    event_key=dsconf.eventKey,
                    component_title=dsconf.params['contexttitle'],
                    device=config.id,
                    component=dsconf.component
                )
            )
            parsed_results['events'].extend(ag_prop_value_events)

        log.debug('MSSQL Availability Group monitoring parsed results: {}'.format(parsed_results))

        return parsed_results


gsm.registerUtility(PowershellMSSQLAlwaysOnAGStrategy(), IStrategy, 'powershell MSSQL AO AG')


class PowershellMSSQLAlwaysOnARStrategy(object):
    implements(IStrategy)

    key = 'MSSQLAlwaysOnAR'

    @staticmethod
    def build_command_line(sql_connection, ag_names):
        ps_command = "powershell -NoLogo -NonInteractive " \
                     "-OutputFormat TEXT -Command "

        ps_ao_ar_script = \
            ("$res = New-Object 'system.collections.generic.dictionary[string, object]';"

             "$def_fields = $server.GetDefaultInitFields([Microsoft.SqlServer.Management.Smo.AvailabilityGroup]);"
             "$server.SetDefaultInitFields([Microsoft.SqlServer.Management.Smo.AvailabilityGroup], $def_fields);"
             "$def_fields = $server.GetDefaultInitFields([Microsoft.SqlServer.Management.Smo.AvailabilityReplica]);"
             "$server.SetDefaultInitFields([Microsoft.SqlServer.Management.Smo.AvailabilityReplica], $def_fields);"
             "$dbmaster = $server.Databases['master'];"
             "$ag_names = @(ag_names_placeholder);"

             "foreach ($ag_name in $ag_names) {"
             " $ag = New-Object 'Microsoft.SqlServer.Management.Smo.AvailabilityGroup' $server, $ag_name;"
             " $ag.Refresh();"
             " foreach ($ar in $ag.AvailabilityReplicas) {"
             "   $ar_uid = $ar.UniqueId;"
             '   $ar_info_query = \\"SELECT avail_repl.replica_server_name AS rep_srv_name,'
             "   ISNULL(av_repl_st.synchronization_health, 100) AS sync_hth"
             "   FROM sys.availability_replicas AS avail_repl"
             "   LEFT JOIN sys.dm_hadr_availability_replica_states AS av_repl_st"
             "   ON avail_repl.replica_id = av_repl_st.replica_id"
             '   WHERE avail_repl.replica_id = \'$ar_uid\';\\";'
             "   try {"
             "     $ar_info_res = $dbmaster.ExecuteWithResults($ar_info_query);"
             "     $rep_srv_name = $ar_info_res.tables[0].rows[0].rep_srv_name;"
             "     $sync_hth = $ar_info_res.tables[0].rows[0].sync_hth;"
             "   }"
             "   catch {"
             "     $rep_srv_name = '';"
             "     $sync_hth = '';"
             "   }"
             # Need only replicas from current node. It is possible to pass Availability group names into script to
             # avoid extra work on remote, but if there are lot of replicas - script length may exceed
             # maximum possible length.
             "   if ($rep_srv_name -ne $server.Name) {continue;}"
             "   $ar_inf = New-Object 'System.Collections.Generic.Dictionary[string, object]';"
             "   $ar_inf['id'] = $ar_uid;"
             "   $ar_inf['name'] = $ar.Name;"
             "   $ar_inf['role'] = $ar.Role;"
             "   $ar_inf['state'] = $ar.MemberState;"
             "   $ar_inf['operational_state'] = $ar.OperationalState;"
             "   $ar_inf['availability_mode'] = $ar.AvailabilityMode;"
             "   $ar_inf['connection_state'] = $ar.ConnectionState;"
             "   $ar_inf['synchronization_state'] = $ar.RollupSynchronizationState;"
             "   $ar_inf['failover_mode'] = $ar.FailoverMode;"
             "   $ar_inf['synchronization_health'] = $sync_hth;"
             "   $res[$ar_uid] = $ar_inf;"
             " }"
             "}"
             "$res_in_json = ConvertTo-Json $res;"
             "Write-Host $res_in_json;").replace('ag_names_placeholder',
                                                 ','.join(("'{}'".format(ag_name) for ag_name in ag_names)))
        script = "\"& {{{}}}\"".format(
            ''.join([BUFFER_SIZE] +
                    getSQLAssembly(sql_connection.version) +
                    sql_connection.sqlConnection +
                    [ps_ao_ar_script]))

        log.debug('Powershell MSSQL Always On AR Strategy script: {}'.format(script))

        return ps_command, script

    @staticmethod
    def parse_result(config, result):

        datasources = config.datasources

        parsed_results = PythonDataSourcePlugin.new_data()

        if result.stderr:
            log.debug('MSSQL AO AR error: {0}'.format('\n'.join(result.stderr)))
        log.debug('MSSQL AO AR results: {}'.format('\n'.join(result.stdout)))

        if result.exit_code != 0:
            log.debug(
                'Non-zero exit code ({0}) for MSSQL AO AR on {1}'.format(
                    result.exit_code, datasources[0].cluster_node_server))
            return parsed_results

        # Parse values
        ar_info_stdout = filter_sql_stdout(result.stdout)
        availability_replicas_info, passing_error = parse_winrs_response(ar_info_stdout, 'json')

        if not availability_replicas_info and passing_error:
            log.debug('Error during parsing Availability Replicas performance data')
            return parsed_results

        log.debug('Availability Replicas performance response: {}'.format(availability_replicas_info))

        if not availability_replicas_info:
            log.debug('Got empty Availability replica response for {}'.format(datasources[0].cluster_node_server))
            availability_replicas_info = {}  # need for further setting of default values.

        for dsconf in datasources:
            ar_id = dsconf.params.get('instanceid')

            ar_name = dsconf.params.get('contexttitle')
            ar_results = availability_replicas_info.get(ar_id)

            if not ar_results:
                log.debug('Got empty monitoring response for Availability Replica {}.'.format(ar_name))
                # We got empty result for particular Availability Replica - seems like it is unreachable.
                # Need to return set of properties with default values
                ar_results = get_default_properties_value_for_component('WinSQLAvailabilityReplica')

            # Maps:
            ar_om = ObjectMap()
            ar_om.id = dsconf.params['instanceid']
            ar_om.title = dsconf.params['contexttitle']
            ar_om.compname = dsconf.params['contextcompname']
            ar_om.modname = dsconf.params['contextmodname']
            ar_om.relname = dsconf.params['contextrelname']
            ar_om = fill_ar_om(ar_om, ar_results, prepId, {})
            parsed_results['maps'].append(ar_om)

            # Events:
            ar_events = get_prop_value_events(
                'WinSQLAvailabilityReplica',
                ar_om.__dict__,
                dict(
                    event_class=dsconf.eventClass or "/Status",
                    event_key=dsconf.eventKey,
                    component_title=dsconf.params['contexttitle'],
                    device=config.id,
                    component=dsconf.component
                )
            )
            for event in ar_events:
                parsed_results['events'].append(event)

        log.debug('MSSQL Availability Replica performance results: {}'.format(parsed_results))

        return parsed_results


gsm.registerUtility(PowershellMSSQLAlwaysOnARStrategy(), IStrategy, 'powershell MSSQL AO AR')


class PowershellMSSQLAlwaysOnALStrategy(object):
    implements(IStrategy)

    key = 'AlwaysOnAL'

    @staticmethod
    def build_command_line(listener_id):
        ps_command = "powershell -NoLogo -NonInteractive " \
                     "-OutputFormat TEXT -Command "

        ps_ao_al_script = \
            ("Import-Module FailoverClusters;"
             "$listener_info = New-Object 'system.collections.generic.dictionary[string,string]';"

             "$ips_dict = New-Object 'system.collections.generic.dictionary[string,object]';"
             "$al = $null;"
             "$cluster_resources = Get-ClusterResource | Where-Object {$_.Id -like 'al_id_placeholder' -or $_.ResourceType -like 'IP Address'};"
             "foreach ($res in $cluster_resources) {"
             " if ($res.Id -like 'al_id_placeholder') {"
             "  $al = $res;"
             "}"
             " if ($res.ResourceType -like 'IP Address') {"
             "  $ips_dict[$res.Name] = $res;"
             " }"
             "}"

             "if ($al -ne $null) {"
             " $dns_name = Get-ClusterParameter -InputObject $al -name DnsName | Select-Object -Property Value;"
             " $listener_info['name'] = $al.Name;"
             " $listener_info['dns_name'] = $dns_name.Value;"
             " $listener_info['state'] = $al.State.value__;"

             " $al_dependency = Get-ClusterResourceDependency -InputObject $al;"
             " if ($al_dependency.DependencyExpression -match '\(?\[([\w.\- ]+)+\]\)?') {"
             "  $al_dep_name = $Matches[$Matches.Count-1];"
             "  $ip_address_res = $null;"
             "  if ($ips_dict.TryGetValue($al_dep_name, [ref]$ip_address_res)) {"
             "   $ip_address = Get-ClusterParameter -InputObject $ip_address_res -name Address | Select-Object -Property Value;"
             "   $listener_info['ip_address'] = $ip_address.Value;"
             "  }"
             " }"
             "}"
             "$listener_info_json = ConvertTo-Json $listener_info;"
             "write-host $listener_info_json;").replace('al_id_placeholder', listener_id)

        script = "\"& {{{}}}\"".format(ps_ao_al_script)

        log.debug('Powershell MSSQL Always On AL Strategy script: {}'.format(script))

        return ps_command, script

    @staticmethod
    def parse_result(config, result):

        dsconf0 = config.datasources[0]
        al_id = dsconf0.params.get('instanceid')
        al_name = dsconf0.params.get('contexttitle')

        parsed_results = PythonDataSourcePlugin.new_data()

        if result.stderr:
            log.debug('MSSQL AO AL error: {0}'.format('\n'.join(result.stderr)))
        log.debug('MSSQL AO AL results: {}'.format('\n'.join(result.stdout)))

        if result.exit_code != 0:
            log.debug(
                'Non-zero exit code ({0}) for MSSQL AO AL with ID {1}'.format(
                    result.exit_code, al_id))
            return parsed_results

        # Parse values
        al_info_stdout = filter_sql_stdout(result.stdout)
        availability_listener_info, passing_error = parse_winrs_response(al_info_stdout, 'json')

        if not availability_listener_info and passing_error:
            log.debug('Error during parsing Availability Listener performance data')
            return parsed_results

        log.debug('Availability Listener performance response: {}'.format(availability_listener_info))

        if not availability_listener_info:
            log.debug('Got empty monitoring response for Availability Listener {}.'.format(al_name))
            # We got empty result for particular Availability Listener - seems like it is unreachable.
            # Need to return set of properties with default values
            availability_listener_info = get_default_properties_value_for_component('WinSQLAvailabilityListener')

        # Maps:
        al_om = ObjectMap()
        al_om.id = dsconf0.params['instanceid']
        al_om.title = dsconf0.params['contexttitle']
        al_om.compname = dsconf0.params['contextcompname']
        al_om.modname = dsconf0.params['contextmodname']
        al_om.relname = dsconf0.params['contextrelname']
        al_om = fill_al_om(al_om, availability_listener_info, prepId)
        parsed_results['maps'].append(al_om)

        # Events:
        ar_events = get_prop_value_events(
            'WinSQLAvailabilityListener',
            al_om.__dict__,
            dict(
                event_class=dsconf0.eventClass or "/Status",
                event_key=dsconf0.eventKey,
                component_title=dsconf0.params['contexttitle'],
                device=config.id,
                component=dsconf0.component
            )
        )
        for event in ar_events:
            parsed_results['events'].append(event)

        log.debug('MSSQL Availability Listener performance results: {}'.format(parsed_results))

        return parsed_results


gsm.registerUtility(PowershellMSSQLAlwaysOnALStrategy(), IStrategy, 'powershell AO AL')


class PowershellMSSQLAlwaysOnADBStrategy(object):
    implements(IStrategy)

    key = 'MSSQLAlwaysOnADB'

    @staticmethod
    def build_command_line(sql_connection, adb_indices, counters):
        ps_command = "powershell -NoLogo -NonInteractive " \
                     "-OutputFormat TEXT -Command "

        ps_adb_script = (
            # Need to SMO object instead T-SQL, because sys.Databases doesn't have State while SMO has.
            "$opt_tps = @([Microsoft.SqlServer.Management.Smo.AvailabilityGroup], [Microsoft.SqlServer.Management.Smo.Database], [Microsoft.SqlServer.Management.Smo.Table]);"
            "foreach ($ot in $opt_tps) {"
            " $def = $server.GetDefaultInitFields($ot);"
            " $server.SetDefaultInitFields($ot, $def);"
            "}"
            "$dtp = 'system.collections.generic.dictionary[string,object]';"
            "$res = New-Object $dtp;"
            "$res['model_data'] = New-Object $dtp;"
            "$res['perf_data'] = New-Object $dtp;"
            # Status determination section:
            "if ($server.Databases -ne $null) {"
            " $ags = New-Object $dtp;"
            " $db_names = New-Object System.Collections.ArrayList;"
            " $db_names_id_map = New-Object $dtp;"

            " $dbMaster = $server.Databases['master'];"
            # We use DB index instead names or Unique ID because we pass them into script
            # and script may goes beyond max script length.
            " foreach ($db in $server.Databases | Where-Object {$_.ID -In @(db_indices_placeholder)}) {"
            "  $mod_inf = New-Object $dtp;"
            "  $db_name = $db.Name;"
            "  $db_names.Add(\\\"'$db_name'\\\") > $null;"
            "  $db_names_id_map[$db_name] = $db.ID;"

            "  $mod_inf['status'] = [string]$db.Status;"
            #  AO Related data:
            "  $ag_name = $db.AvailabilityGroupName;"
            "  if ($ag_name) {"
            "   $ag = $null;"
            "   if (-not $ags.TryGetValue($ag_name, [ref]$ag)) {"
            "    $ag = New-Object 'Microsoft.SqlServer.Management.Smo.AvailabilityGroup' $server, $ag_name;"
            "    $ags[$ag_name] = $ag;"
            "   }"

            "   if ($ag -ne $null) {"
            "    $adb = New-Object 'Microsoft.SqlServer.Management.Smo.AvailabilityDatabase' $ag, $db_name;"
            "    $adb.Refresh();"
            "    $mod_inf['sync_state'] = $adb.SynchronizationState;"
            "    $mod_inf['suspended'] = $adb.IsSuspended;"
            "   }"
            "  }"
            "  $res['model_data'][$db.ID] = $mod_inf;"
            " }"
            " $db_names_str = $db_names -join ', ';"
            # Performance counters section:"
            " $query = \\\"SELECT RTRIM(instance_name) AS ins_name,"
            " RTRIM(counter_name) AS c_name,"
            " RTRIM(cntr_value) AS cntr_value"
            " FROM sys.dm_os_performance_counters"
            " WHERE instance_name IN ($db_names_str)"
            " AND counter_name IN (counters_placeholder);\\\";"
            " $db_res = $dbMaster.ExecuteWithResults($query); "
            " if ($db_res.Tables[0].rows.count -gt 0) {"
            "  $db_res.Tables[0].rows | ForEach-Object {"
            "   $db_id = $db_names_id_map[$_.ins_name];"
            "   if ($db_id) {"
            "    if (-Not $res['perf_data'].Keys.Contains($db_id)) {"
            "     $res['perf_data'][$db_id] = New-Object $dtp;"
            "    }"
            "    $res['perf_data'][$db_id][$_.c_name] = $_.cntr_value;"
            "   }"
            "  }"
            " }"
            "}"
            "$res_json = ConvertTo-Json $res;"
            "write-host $res_json;").replace('db_indices_placeholder',
                                             ','.join(("'{}'".format(adb_index) for adb_index in adb_indices)))

        ps_adb_script = ps_adb_script.replace('counters_placeholder',
                                              ','.join(("'{}'".format(counter)
                                                        for counter in set(counters)  # use set to make values unique
                                                        if counter)))

        script = "\"& {{{}}}\"".format(
            ''.join([BUFFER_SIZE] +
                    getSQLAssembly(sql_connection.version) +
                    sql_connection.sqlConnection +
                    [ps_adb_script]))

        log.debug('Powershell MSSQL Always On ADB Strategy script: {}'.format(script))

        return ps_command, script

    @staticmethod
    def parse_result(config, result):
        datasources = config.datasources

        parsed_results = PythonDataSourcePlugin.new_data()

        if result.stderr:
            log.debug('MSSQL AO ADB error: {0}'.format('\n'.join(result.stderr)))
        log.debug('MSSQL AO ADB results: {}'.format('\n'.join(result.stdout)))

        if result.exit_code != 0:
            log.debug(
                'Non-zero exit code ({0}) for MSSQL AO ADB on {1}'.format(
                    result.exit_code, datasources[0].cluster_node_server))
            return parsed_results

        # Parse values
        adb_info_stdout = filter_sql_stdout(result.stdout)
        availability_database_info, passing_error = parse_winrs_response(adb_info_stdout, 'json')

        if not availability_database_info and passing_error:
            log.debug('Error during parsing Availability Databases performance data')
            return parsed_results

        log.debug('Availability Databases performance response: {}'.format(availability_database_info))

        if not availability_database_info:
            log.debug('Got empty Availability Databases monitoring response')
            availability_database_info = {}  # need for further processing

        # Get modeling and performance data from response
        model_data = availability_database_info.get('model_data', {})
        perf_data = availability_database_info.get('perf_data', {})

        for dsconf in datasources:
            adb_index = dsconf.params.get('database_index')
            adb_title = dsconf.params.get('contexttitle')

            if dsconf.datasource == 'status':  # Maps & Events ships in scope of 'status' datasource
                # Maps:
                adb_model_results = model_data.get(adb_index)
                if not adb_model_results:
                    log.debug('Got empty medeling response for Availability Database {}.'.format(adb_title))
                    # We got empty result for particular Availability Database - seems like it is unreachable.
                    # Need to return set of properties with default values
                    adb_model_results = get_default_properties_value_for_component('WinSQLDatabase')

                # As for Databases - status takes from 'status' RRD datapoint - populate it.
                status_value = adb_model_results.get('status', None)
                parsed_results['values'][dsconf.component]['status'] = lookup_database_status(status_value), 'N'

                adb_om = ObjectMap()
                adb_om.id = dsconf.params['instanceid']
                adb_om.title = adb_title
                adb_om.compname = dsconf.params['contextcompname']
                adb_om.modname = dsconf.params['contextmodname']
                adb_om.relname = dsconf.params['contextrelname']
                adb_om = fill_adb_om(adb_om, adb_model_results, prepId)
                parsed_results['maps'].append(adb_om)

                # Events:
                # DB Status (status), suspended, sync_state
                adb_events_data = adb_om.__dict__
                adb_events_data['status'] = status_value
                adb_events = get_prop_value_events(
                    'WinSQLDatabase',
                    adb_events_data,
                    dict(
                        event_class=get_valid_dsconf(datasources) or "/Status",
                        event_key=dsconf.eventKey,
                        component_title=dsconf.params['contexttitle'],
                        device=config.id,
                        component=dsconf.component
                    )
                )
                for event in adb_events:
                    parsed_results['events'].append(event)

            # Metrics
            adb_perf_results = perf_data.get(adb_index)
            if not adb_perf_results:
                log.debug('Got empty performance response for Availability Database {}.'.format(adb_title))
                # We got empty result for particular Availability Database - seems like it is unreachable.
                # Need to return set of properties with default values
                adb_perf_results = {}

            dp_key = dsconf.params['resource']
            dp_value = adb_perf_results.get(dp_key)
            if dp_value is not None and len(dsconf.points) > 0:
                # datasource has 1 datapoint
                parsed_results['values'][dsconf.component][dsconf.points[0].id] = dp_value,\
                                                                                  int(time.mktime(time.localtime()))

        log.debug('MSSQL Availability Databases performance results: {}'.format(parsed_results))

        return parsed_results


gsm.registerUtility(PowershellMSSQLAlwaysOnADBStrategy(), IStrategy, 'powershell MSSQL AO ADB')


class ShellDataSourcePlugin(PythonDataSourcePlugin):

    proxy_attributes = ConnectionInfoProperties + (
        'sqlhostname',
        'cluster_node_server'
    )
    start = None

    @classmethod
    def config_key(cls, datasource, context):
        """
        Uniquely pull in datasources
        """
        if datasource.strategy == 'Custom Command':
            return (context.device().id,
                    datasource.getCycleTime(context),
                    datasource.strategy,
                    datasource.id,
                    context.id)
        elif datasource.strategy == 'powershell MSSQL' or \
                datasource.strategy == 'powershell MSSQL Job':
            # allow for existing zDBInstances
            return (context.device().id,
                    datasource.getCycleTime(context),
                    datasource.strategy,
                    getattr(context, 'instancename', ''))
        elif datasource.strategy == 'powershell MSSQL AO AG' or \
                datasource.strategy == 'powershell MSSQL AO AR' or \
                datasource.strategy == 'powershell MSSQL AO ADB':
            # TODO: single out 'powershell MSSQL AO ...' into separate config key, as 'cluster_node_server' value
            #  should be included as well. It is also true for 'powershell MSSQL' and 'powershell MSSQL Job' strategies.
            #  As a result, when 'cluster_node_server' will be included to theirs config key - this particular block
            #  should be removed and 'powershell MSSQL AO ...' strategies name should
            #  be added to the previous elif block.
            return (context.device().id,
                    datasource.getCycleTime(context),
                    datasource.strategy,
                    getattr(context, 'instancename', ''),
                    getattr(context, 'cluster_node_server', ''))
        elif datasource.strategy == 'powershell MSSQL Instance':
            return (context.device().id,
                    datasource.getCycleTime(context),
                    datasource.strategy,
                    getattr(context, 'instancename', ''),
                    context.id)
        return (context.device().id,
                datasource.getCycleTime(context),
                datasource.strategy,
                context.id)

    @classmethod
    def params(cls, datasource, context):
        resource = datasource.talesEval(datasource.resource, context)
        if not resource.startswith('\\') and \
            datasource.strategy not in ('powershell MSSQL',
                                        'Custom Command',
                                        'DCDiag',
                                        'powershell MSSQL Instance',
                                        'powershell MSSQL Job,'
                                        'powershell MSSQL AO AG',
                                        'powershell MSSQL AO AR',
                                        'powershell AO AL',
                                        'powershell MSSQL AO ADB'):
            resource = '\\' + resource
        if safe_hasattr(context, 'perfmonInstance') and context.perfmonInstance is not None:
            resource = context.perfmonInstance + resource

        instancename = getattr(context, 'instancename', '')

        instanceid = getattr(context, 'id', '')

        version = getattr(context, 'sql_server_version', 0)
        if version:
            # ensure version is a string
            match = re.match('(\d+)\..*', str(version))
            if match:
                version = match.groups()[0]
            else:
                version = 0

        owner_node_ip = None
        if hasattr(context, 'cluster_node_server'):
            cluster_node_server = context.cluster_node_server
            if isinstance(cluster_node_server, str) and '//' in cluster_node_server:
                owner_node, _ = cluster_node_server.split('//')
                owner_node_ip = getattr(context, 'owner_node_ip', None)
                if not owner_node_ip:
                    try:
                        owner_node_ip = context.device().clusterhostdevicesdict.get(owner_node, None)
                    except Exception:
                        pass

        try:
            contextURL = context.getPrimaryUrlPath()
            deviceURL = urlparse(context.getParentDeviceUrl())
            contextInstance = urllib.quote("/".join((context.getParentNode().id, context.id)))
            contextcompname = contextURL[len(deviceURL.path) + 1:-len(contextInstance) - 1]
            contextrelname = context.getParentNode().id
            contextmodname = context.__module__

        except(AttributeError):
            contextmodname = ''
            contextrelname = ''
            contextcompname = ''

        contexttitle = context.title

        servername = context.device().title

        if len(servername) == 0:
            servername = ''

        parser = getParserLoader(context.dmd, datasource.parser)

        script = get_script(datasource, context)

        # Always On params:
        # SQL Instance ID from relation.
        get_winsqlinstance = getattr(context, 'get_winsqlinstance', None)
        if get_winsqlinstance:
            winsqlinstance_id = get_winsqlinstance()
        else:
            winsqlinstance_id = None
        # Availability Group name for containing objects.
        availability_group_name = getattr(context, 'availability_group_name', '')
        # Database ID (Index)
        database_index = getattr(context, 'db_id', None)
        # Database Monitoring Ignored Statuses
        db_ignored_statuses = getattr(context, 'zWinDBStateMonitoringIgnore', [])
        return dict(resource=resource,
                    strategy=datasource.strategy,
                    instancename=instancename,
                    instanceid=instanceid,
                    servername=servername,
                    script=script,
                    parser=parser,
                    usePowershell=datasource.usePowershell,
                    contextrelname=contextrelname,
                    contextcompname=contextcompname,
                    contextmodname=contextmodname,
                    contexttitle=contexttitle,
                    version=version,
                    owner_node_ip=owner_node_ip,
                    winsqlinstance_id=winsqlinstance_id,
                    availability_group_name=availability_group_name,
                    database_index=database_index,
                    db_ignored_statuses=db_ignored_statuses)

    def getSQLConnection(self, dsconf, conn_info):
        dbinstances = dsconf.zDBInstances
        username = dsconf.windows_user
        password = dsconf.windows_password
        dblogins = parseDBUserNamePass(
            dbinstances, username, password
        )

        # complete instance name should now always be in cluster_node_server
        # cluster ex. sol-win03.solutions-wincluster.loc//SQL1 for MSSQLSERVER
        # sol-win03.solutions-wincluster.loc//SQL3\TESTINSTANCE1 for TESTINSTANCE1
        # standalone ex. //SQLHOSTNAME for MSSQLSERVER
        # //SQLTEST\TESTINSTANCE1
        if dsconf.cluster_node_server:
            owner_node, server = dsconf.cluster_node_server.split('//')
            if owner_node:
                conn_info = conn_info._replace(hostname=owner_node)
                conn_info = conn_info._replace(ipaddress=dsconf.params['owner_node_ip'])
            instance_name = server

        instance = dsconf.params['instancename']
        try:
            if len(instance_name.split('\\')) < 2:
                instance_login = dblogins['MSSQLSERVER']
            else:
                instance_login = dblogins[instance]
        except NameError:
            raise WindowsShellException(
                "Cannot determine sql server name for {} on {}.  Remodel device.".format(instance, dsconf.device))
        except KeyError:
            log.debug("zDBInstances does not contain credentials for %s.  "
                      "Using default credentials" % instance)
            try:
                instance_login = dblogins['MSSQLSERVER']
            except KeyError:
                instance_login = {'username': dsconf.windows_user,
                                  'password': dsconf.windows_password,
                                  'login_as_user': True}

        sqlConnection = SqlConnection(instance_name,
                                      instance_login['username'],
                                      instance_login['password'],
                                      instance_login['login_as_user'],
                                      dsconf.params['version'])
        return sqlConnection, conn_info

    @coroutine
    def collect(self, config):
        dsconf0 = config.datasources[0]
        conn_info = createConnectionInfo(dsconf0)

        strategy = queryUtility(IStrategy, dsconf0.params['strategy'])
        if not strategy:
            raise WindowsShellException(
                "No strategy chosen for {0}".format(dsconf0.datasource)
            )

        counters = [dsconf.params['resource'] for dsconf in config.datasources]

        if dsconf0.params['strategy'].startswith('powershell MSSQL'):
            cmd_line_input, conn_info = self.getSQLConnection(dsconf0,
                                                              conn_info)
            if dsconf0.params['strategy'] == 'powershell MSSQL Instance':
                owner_node, server = dsconf.cluster_node_server.split('//')
                if len(server.split('\\')) < 2:
                    cmd_line_input = 'MSSQLSERVER'
                else:
                    cmd_line_input = dsconf0.params['instancename']  # instancename represents native SQL Instance name.
            if dsconf.params['strategy'] == 'powershell MSSQL' or\
                    dsconf.params['strategy'] == 'powershell MSSQL Job':
                conn_info = conn_info._replace(timeout=dsconf0.cycletime - 5)

            if dsconf0.params['strategy'] == 'powershell MSSQL AO AG':
                # For Always On Availability groups, Availability Group names are needed:
                ag_nemes = [dsconf.params['contexttitle']
                            for dsconf in config.datasources
                            if dsconf.params['contexttitle']]
                command_line, script = strategy.build_command_line(cmd_line_input, ag_nemes)
            elif dsconf0.params['strategy'] == 'powershell MSSQL AO AR':
                # For Always On Availability replicas, we need the replicas' Availability Group names:
                ag_nemes = [dsconf.params['availability_group_name']
                            for dsconf in config.datasources
                            if dsconf.params['availability_group_name']]
                command_line, script = strategy.build_command_line(cmd_line_input, ag_nemes)
            elif dsconf.params['strategy'] == 'powershell MSSQL AO ADB':
                conn_info = conn_info._replace(timeout=dsconf0.cycletime - 5)  # TODO: revise whether this is still needed.
                # DB Indices
                db_indices = {dsconf.params['database_index']
                              for dsconf in config.datasources
                              if dsconf.params['database_index'] is not None}
                command_line, script = strategy.build_command_line(cmd_line_input, db_indices, counters)
            else:
                command_line, script = strategy.build_command_line(cmd_line_input)
        elif dsconf0.params['strategy'] == 'powershell AO AL':
            cmd_line_input = dsconf0.params.get('instanceid', '')  # Take listener ID as input parameter.
            command_line, script = strategy.build_command_line(cmd_line_input)
        elif dsconf0.params['strategy'] == 'Custom Command':
            check_datasource(dsconf0)
            script = dsconf0.params['script']
            usePowershell = dsconf0.params['usePowershell']
            command_line, script = strategy.build_command_line(script, usePowershell)
        elif dsconf0.params['strategy'] == 'DCDiag':
            testparms = [dsconf.params['script'] for dsconf in config.datasources if dsconf.params['script']]
            command_line = strategy.build_command_line(counters, testparms, dsconf0.windows_user, dsconf0.windows_password)
            conn_info = conn_info._replace(timeout=180)
            script = None
        else:
            command_line, script = strategy.build_command_line(counters)

        command = SingleCommandClient(conn_info)
        self.start = time.mktime(time.localtime())
        results = yield command.run_command(command_line, script)

        defer.returnValue((strategy, config.datasources, results))

    @save
    def onSuccess(self, results, config):
        elapsed = time.mktime(time.localtime()) - self.start
        log.debug('%s Shell query took %d seconds', config.id, elapsed)
        data = self.new_data()
        dsconf0 = config.datasources[0]
        severity = ZenEventClasses.Clear
        msg = 'winrs: successful collection'
        components = set([ds.component for ds in config.datasources])

        if not results:
            return data

        strategy, dsconfs, result = results
        log.debug('results: {}'.format(result))
        if strategy.key == 'CustomCommand':
            cmdResult = strategy.parse_result(config, result)
            data['events'] = cmdResult.events
            if result.exit_code == 0:
                dsconf = dsconfs[0]
                for dp, value in cmdResult.values:
                    data['values'][dsconf.component][dp.id] = value, 'N'
            elif len(cmdResult.values) != 0:
                dsconf = dsconfs[0]
                for dp, value in cmdResult.values:
                    data['values'][dsconf.component][dp.id] = value, 'N'
        elif strategy.key == 'DCDiag':
            diagResult = strategy.parse_result(config, result)
            dsconf = dsconfs[0]
            data['events'] = diagResult.events
        elif strategy.key == 'MSSQLJob':
            diagResult = strategy.parse_result(dsconfs, result)
            dsconf = dsconfs[0]
            data['events'] = diagResult.events
        elif strategy.key in ('MSSQLAlwaysOnAG', 'MSSQLAlwaysOnAR', 'AlwaysOnAL', 'MSSQLAlwaysOnADB'):
            ao_result = strategy.parse_result(config, result)
            data['values'] = ao_result.get('values', {})
            data['maps'] = ao_result.get('maps', [])
            data['events'] = ao_result.get('events', [])
        elif strategy.key == 'MSSQLInstance':
            for dsconf, value in strategy.parse_result(dsconfs, result):
                currentstate = {
                    'Running': ZenEventClasses.Clear,
                    'Stopped': dsconf.severity
                }.get(value[1], ZenEventClasses.Info)

                summary = 'MSSQL Instance {0} is {1}.'.format(
                    dsconf.component,
                    value[1].strip()
                )

                data['events'].append(dict(
                    eventClass=dsconf.eventClass or '/Status',
                    eventClassKey='winrsCollection {0}'.format(strategy.key),
                    eventKey=strategy.key,
                    severity=currentstate,
                    summary=summary,
                    device=config.id,
                    component=prepId(dsconf.component)
                ))
        else:
            if len(result.stdout) < 2 and strategy.key == "PowershellMSSQL":
                try:
                    db_name = result.stdout[0].split(':')[1]
                except IndexError:
                    db_name = dsconf0.component
                msg = 'There is no monitoring data for the database "{0}"'.format(db_name)
                severity = ZenEventClasses.Info

                if result.stderr:
                    inst_err = dsconfs[0].params['instancename']
                    msg = []
                    for e in result.stderr:
                        if inst_err in e:
                            severity = ZenEventClasses.Critical
                        if 'At line:' in e:
                            break
                        msg.append(re.sub('[".]', '', e))
                    msg = ''.join(msg)
            else:
                checked_result = False
                for dsconf, value, timestamp in strategy.parse_result(dsconfs, result):
                    checked_result = True
                    if dsconf.datasource != 'status' or\
                       (dsconf.datasource == 'status' and strategy.key != "PowershellMSSQL"):
                        data['values'][dsconf.component][dsconf.datasource] = value, timestamp
                if strategy.key == 'PowershellMSSQL':
                    # get db status only if status datasource is being one of our dsconfs
                    dsnames = set([dsconf.datasource for dsconf in dsconfs])
                    if 'status' in dsnames:
                        get_eventClass = get_valid_dsconf(dsconfs)
                        for db in getattr(strategy, 'valuemap', []):
                            # only set if status is our only datasource
                            if not set('status').symmetric_difference(dsnames):
                                checked_result = True
                            dsconf = get_dsconf(dsconfs, db, param='contexttitle')
                            if dsconf:
                                component = prepId(dsconf.component)
                                eventClass = dsconf.eventClass or get_eventClass
                            else:
                                component = prepId(db)
                                eventClass = get_eventClass
                            try:
                                dbstatuses = strategy.valuemap[db]['status']
                            except Exception:
                                dbstatuses = 'Unknown'
                            db_summary = ''
                            status = 0
                            severity = ZenEventClasses.Info
                            warnings = ('EmergencyMode', 'Inaccessible', 'Suspect')
                            for dbstatus in dbstatuses.split(','):
                                # create bitmask for status display
                                status += lookup_database_status(dbstatus)
                                # determine severity
                                if dbstatus in warnings:
                                    severity = ZenEventClasses.Warning
                                elif dbstatus == 'Normal':
                                    severity = ZenEventClasses.Clear
                                if db_summary:
                                    db_summary += ' '
                                db_summary += lookup_databasesummary(dbstatus)
                            summary = 'Database {0} status is {1}.'.format(db,
                                                                           dbstatuses)
                            if component in components:
                                data['events'].append(dict(
                                    eventClass=eventClass,
                                    eventClassKey='WinDatabaseStatus',
                                    eventKey=strategy.key,
                                    severity=severity,
                                    device=config.id,
                                    summary=summary,
                                    message=db_summary,
                                    dbstatus=dbstatuses,
                                    component=component
                                ))
                                data['values'][dsconf.component]['status'] = status, 'N'
                                db_om = get_db_om(dsconf, {
                                    'status': status
                                })
                                data['maps'].append(db_om)
                if not checked_result:
                    msg = 'Error parsing data in {0} strategy for "{1}"'\
                        ' datasource'.format(
                            dsconf0.params['strategy'],
                            dsconf0.datasource,
                        )
                    severity = ZenEventClasses.Warning

        if strategy.key == "PowershellMSSQL" or strategy.key == "MSSQLAlwaysOnADB":
            instances = {dsc.component for dsc in dsconfs}
            if msg == 'winrs: successful collection':
                severity = ZenEventClasses.Clear
            for i in list(instances):
                data['events'].append(dict(
                    severity=severity,
                    eventClass=dsconf0.eventClass or "/Status",
                    eventClassKey='winrsCollection',
                    eventKey='winrsCollection {}'.format(
                        dsconf0.params['contexttitle']
                    ),
                    summary=msg,
                    component=i,
                    device=config.id))
        else:
            data['events'].append(dict(
                severity=severity,
                eventClass=dsconf0.eventClass or "/Status",
                eventClassKey='winrsCollection',
                eventKey='winrsCollection {}'.format(
                    dsconf0.params['contexttitle']
                ),
                summary=msg,
                component=dsconf0.component,
                device=config.id))

        data['events'].append(dict(
            severity=ZenEventClasses.Clear,
            eventClassKey='winrsCollectionSuccess',
            eventKey='winrsCollection',
            summary='winrs: successful collection',
            device=config.id))

        # Clear warning events created for specific datasources,
        # e.g. when paster/script not chosen.
        data['events'].append(dict(
            severity=ZenEventClasses.Clear,
            eventClassKey='winrsCollectionError',
            eventKey='datasourceWarning_{0}'.format(dsconf0.datasource),
            summary='Monitoring ok',
            device=config.id))

        # Clear previous error event
        data['events'].append(dict(
            severity=ZenEventClasses.Clear,
            eventClass='/Status',
            eventKey='winrsCollection',
            summary='Monitoring ok',
            device=config.id))

        generateClearAuthEvents(config, data['events'])

        return data

    @save
    def onError(self, result, config):
        log.debug('ShellDataSource error on {}: {}'.format(config.id, result))
        logg = log.error
        msg, event_class = check_for_network_error(
            result, config, default_class='/Status/Winrm')
        eventKey = 'winrsCollection'
        if isinstance(result, Failure):
            if isinstance(result.value, WindowsShellException):
                eventKey = 'datasourceWarning_{0}'.format(
                    config.datasources[0].datasource
                )
                msg = '{0} on {1}'.format(str(result.value), config)
                logg = log.warn
            elif isinstance(result.value, RequestError):
                args = result.value.args
                msg = args[0] if args else format_exc(result.value)
            elif send_to_debug(result):
                logg = log.debug

        msg = 'ShellDataSourcePlugin: ' + msg
        logg(msg)
        data = self.new_data()
        if not errorMsgCheck(config, data['events'], result.value.message):
            data['events'].append(dict(
                severity=ZenEventClasses.Warning,
                eventClass='/Status',
                eventKey=eventKey,
                summary='WinRS: ' + msg,
                device=config.id))
        return data


def check_datasource(dsconf):
    '''
    Check whether the data is correctly filled in datasource.
    '''
    # Check if the parser is chosen.
    if not dsconf.params['parser']:
        raise WindowsShellException(
            "No parser chosen for {0}".format(dsconf.datasource)
        )
    # Check if script was entered.  if not, could be bad syntax
    if not dsconf.params['script']:
        raise WindowsShellException(
            'Either no script was entered or script has invalid syntax on {0}'.format(
                dsconf.datasource)
        )


def parse_stdout(result, check_stderr=False):
    '''
    Get cmd result list with string elements separated by "|" inside,
    and return list of requested values or None, if there are no elements.
    '''
    if check_stderr:
        stderr = ''.join(getattr(result, 'stderr', [])).strip()
        if stderr:
            raise WindowsShellException(stderr)
    try:
        stdout = ''.join(result.stdout).split('|')
    except AttributeError:
        return
    if filter(None, stdout):
        return stdout


def pscommand():
    return "powershell -NoLogo -NonInteractive -NoProfile " \
        "-OutputFormat TEXT -Command "


def get_script(datasource, context):
    '''return single or multiline formatted script'''
    te = lambda x: datasource.talesEval(x, context)
    try:
        script = te(' '.join(string_to_lines(datasource.script)))
    except Exception:
        script = ''
        log.error('Invalid tales expression in custom command script: %s' %
                  str(datasource.script))
    return script


def get_valid_dsconf(dsconfs):
    '''return a valid eventClass'''
    for dsconf in dsconfs:
        if dsconf.eventClass != '':
            return dsconf.eventClass
    return '/Status'
