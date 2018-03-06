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

from ..twisted_utils import add_timeout
from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
from ZenPacks.zenoss.Microsoft.Windows.utils import filter_sql_stdout, \
    parseDBUserNamePass, getSQLAssembly
from ..utils import (
    check_for_network_error, save, errorMsgCheck,
    generateClearAuthEvents, get_dsconf,
    lookup_databasesummary, lookup_database_status)
from EventLogDataSource import string_to_lines
from . import send_to_debug


# Requires that txwinrm_utils is already imported.
from txwinrm.util import RequestError
from txwinrm.WinRMClient import SingleCommandClient
from txwinrm.shell import create_long_running_command, CommandResponse


log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
WINRS_SOURCETYPE = 'Windows Shell'
AVAILABLE_STRATEGIES = [
    'Custom Command',
    'powershell MSSQL',
    'DCDiag',
    'powershell MSSQL Instance',
    'powershell MSSQL Job'
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


class SqlConnection(object):

    def __init__(self, instance, sqlusername, sqlpassword, login_as_user, version):
        # Need to modify query where clause.
        # Currently all counters are retrieved for each database
        self.sqlConnection = []
        self.version = version

        # DB Connection Object
        self.sqlConnection.append("$con = new-object "
                                  "('Microsoft.SqlServer.Management.Common.ServerConnection')"
                                  "'{}', '{}', '{}';".format(instance, sqlusername, sqlpassword))

        if login_as_user:
            # Login using windows credentials
            self.sqlConnection.append("$con.LoginSecure=$true;")
            self.sqlConnection.append("$con.ConnectAsUser=$true;")
            # Omit domain part of username
            self.sqlConnection.append("$con.ConnectAsUserName='{0}';".format(sqlusername.split("\\")[-1]))
            self.sqlConnection.append("$con.ConnectAsUserPassword='{0}';".format(sqlpassword))
        else:
            self.sqlConnection.append("$con.Connect();")

        # Connect to Database Server
        self.sqlConnection.append("$server = new-object ('Microsoft.SqlServer.Management.Smo.Server') $con;")


class PowershellMSSQLStrategy(object):
    implements(IStrategy)

    key = 'PowershellMSSQL'

    def build_command_line(self, sqlConnection):
        pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

        # We should not be running this per database.  Bad performance problems when there are
        # a lot of databases.  Run script per instance

        counters_sqlConnection = []
        counters_sqlConnection.append("if ($server.Databases -ne $null) {")
        counters_sqlConnection.append("$dbMaster = $server.Databases['master'];")
        counters_sqlConnection.append("foreach ($db in $server.Databases){")
        counters_sqlConnection.append("$db_name = '';"
                                      "$sp = $db.Name.split($([char]39)); "
                                      "if($sp.length -ge 2){ "
                                      "foreach($i in $sp){ "
                                      "if($i -ne $sp[-1]){ $db_name += $i + [char]39 + [char]39;}"
                                      "else { $db_name += $i;}"
                                      "}} else { $db_name = $db.Name;}")
        counters_sqlConnection.append("$query = 'select instance_name as databasename, "
                                      "counter_name as ckey, cntr_value as cvalue from "
                                      "sys.dm_os_performance_counters where instance_name = '"
                                      " +[char]39+$db_name+[char]39;")
        counters_sqlConnection.append("$ds = $dbMaster.ExecuteWithResults($query);")
        counters_sqlConnection.append('if($ds.Tables[0].rows.count -gt 0) {$ds.Tables| Format-List;}'
                                      'Write-Host "databasename:"$db_name;'
                                      '$status = $db.Status;write-host "databasestatus:"$status;}}')
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
        for counterline in filter_sql_stdout(result.stdout):
            key, value = counterline.split(':', 1)
            if key.strip() == 'databasename':
                databasename = value.strip()
                if databasename not in self.valuemap:
                    self.valuemap[databasename] = {}
            elif key.strip() == 'ckey':
                _counter = value.strip().lower()
            elif key.strip() == 'cvalue':
                self.valuemap[databasename][_counter] = value.strip()
            elif key.strip() == 'databasestatus':
                self.valuemap[databasename]['status'] = value.strip()

        for dsconf in dsconfs:
            if dsconf.params['resource'] == 'status':
                # no need to get status as it's handled differently
                continue
            timestamp = int(time.mktime(time.localtime()))
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
            except Exception:
                msg = 'Missing or no data returned when querying job "{}"'.format(component)
                collectedResults.events.append({
                    'eventClass': eventClass,
                    'severity': dsconf.severity,
                    'eventClassKey': 'winrsCollection MSSQLJob',
                    'eventKey': dsconf.eventKey,
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


class ShellDataSourcePlugin(PythonDataSourcePlugin):

    proxy_attributes = ConnectionInfoProperties + (
        'sqlhostname',
        'cluster_node_server'
    )

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
                                        'powershell MSSQL Job'):
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
            owner_node, _ = context.cluster_node_server.split('//')
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
                    owner_node_ip=owner_node_ip)

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
                    cmd_line_input = dsconf0.params['instanceid']
            if dsconf.params['strategy'] == 'powershell MSSQL':
                conn_info = conn_info._replace(timeout=dsconf0.cycletime - 5)
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
        results = yield command.run_command(command_line, script)

        defer.returnValue((strategy, config.datasources, results))

    @save
    def onSuccess(self, results, config):
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
                    # get db status
                    for db in getattr(strategy, 'valuemap', []):
                        dsconf = get_dsconf(dsconfs, db, param='contexttitle')
                        if dsconf:
                            component = prepId(dsconf.component)
                            eventClass = dsconf.eventClass or "/Status"
                        else:
                            component = prepId(db)
                            eventClass = "/Status"
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
                if not checked_result:
                    msg = 'Error parsing data in {0} strategy for "{1}"'\
                        ' datasource'.format(
                            dsconf0.params['strategy'],
                            dsconf0.datasource,
                        )
                    severity = ZenEventClasses.Warning

        if strategy.key == "PowershellMSSQL":
            instances = {dsc.component for dsc in dsconfs}
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
