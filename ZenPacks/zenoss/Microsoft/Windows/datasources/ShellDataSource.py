##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2016, all rights reserved.
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

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
from ZenPacks.zenoss.Microsoft.Windows.utils import filter_sql_stdout, \
    parseDBUserNamePass, getSQLAssembly
from ..utils import (
    check_for_network_error, pipejoin, sizeof_fmt, cluster_state_value,
    save, errorMsgCheck, generateClearAuthEvents,)
from EventLogDataSource import string_to_lines


# Requires that txwinrm_utils is already imported.
from txwinrm.util import UnauthorizedError, RequestError
from txwinrm.shell import create_single_shot_command

log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
WINRS_SOURCETYPE = 'Windows Shell'
AVAILABLE_STRATEGIES = [
    'Custom Command',
    'powershell MSSQL',
    'powershell Cluster Services',
    'powershell Cluster Resources',
    'powershell Cluster Nodes',
    'powershell Cluster Disks',
    'powershell Cluster Network',
    'powershell Cluster Interface',
    'DCDiag',
    'powershell MSSQL Instance',
    'powershell MSSQL Job'
    ]

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
        try:
            dcuser = '{}\\{}'.format((username.split('@')[1].split('.')[0]), username.split('@')[0])
        except Exception:
            raise WindowsShellException('Username invalid.  Must be in user@example.com format.  Check zWinRMUser: {}'.format(username))
        dcdiagcommand = 'dcdiag /q /u:{} /p:{} /test:'.format(dcuser, password) + ' /test:'.join(tests)
        if testparms:
            dcdiagcommand += ' ' + ' '.join(testparms)
        return dcdiagcommand

    def parse_result(self, config, result):
        if result.stderr:
            log.debug('DCDiag error: {0}' + ''.join(result.stderr))

        dsconf = config.datasources[0]
        output = result.stdout
        collectedResults = ParsedResults()
        tests_in_error = set()
        eventClass = dsconf.eventClass if dsconf.eventClass else "/Status"
        if output:
            error_str = ''
            for line in output:
                # Failure of a test shows the error message first followed by:
                # "......................... <dc> failed test <testname>"
                if line.startswith('........'):
                    #create err event
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

                    collectedResults.events.append({
                        'eventClass': eventClass,
                        'severity': dsconf.severity,
                        'eventClassKey': 'WindowsActiveDirectoryStatus',
                        'eventKey': eventkey,
                        'summary': msg,
                        'device': config.id})
                    error_str = ''
                else:
                    error_str += line if not error_str else ' ' + line
        for diag_test in self.run_tests.difference(tests_in_error):
            # Clear events
            msg = "'DCDiag /test:{}' passed".format(diag_test)
            eventkey = 'WindowsActiveDirectory{}'.format(diag_test)

            collectedResults.events.append({
                'eventClass': eventClass,
                'severity': ZenEventClasses.Clear,
                'eventClassKey': 'WindowsActiveDirectoryStatus',
                'eventKey': eventkey,
                'summary': msg,
                'device': config.id})
        return collectedResults

gsm.registerUtility(DCDiagStrategy(), IStrategy, 'DCDiag')


class CustomCommandStrategy(object):
    implements(IStrategy)

    key = 'CustomCommand'

    def build_command_line(self, script, usePowershell):
        if not usePowershell:
            return script
        script = script.replace('"', "'")
        pscommand = 'powershell -NoLogo -NonInteractive -NoProfile -OutputFormat TEXT ' \
                    '-Command "{0}"'
        return pscommand.format(script)

    def parse_result(self, config, result):
        dsconf = config.datasources[0]
        parserLoader = dsconf.params['parser']
        log.debug('Trying to use the %s parser' % parserLoader.pluginName)

        # Build emulated Zencommand Cmd object
        cmd = WinCmd()
        cmd.setDatasource(dsconf)
        cmd.name = '{}/{}'.format(dsconf.template, dsconf.datasource)
        cmd.command = dsconf.params['script']

        cmd.ds = dsconf.datasource
        cmd.device = dsconf.params['servername']
        cmd.component = dsconf.params['contextcompname']

        # Pass the severity from the datasource to the command parsers
        cmd.severity = dsconf.severity

        # Add the device id to the config for compatibility with parsers
        config.device = config.id
        cmd.deviceConfig = config
        cmd.deviceConfig.name = config.id

        # Add the component id to the points array for compatibility with parsers
        for point in dsconf.points:
            point.component = cmd.component
            cmd.points.append(point)

        cmd.usePowershell = dsconf.params['usePowershell']
        cmd.result.output = '\n'.join(result.stdout)
        cmd.result.exitCode = result.exit_code

        collectedResult = ParsedResults()
        parser = parserLoader.create()
        parser.processResults(cmd, collectedResult)
        # Give error feedback to user
        eventClass = dsconf.eventClass if dsconf.eventClass else "/Status"
        if result.stderr:
            log.debug(result.stderr)
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
                                      'else { Write-Host "databasename:"$db.Name;}}}')
        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(getSQLAssembly(sqlConnection.version) + sqlConnection.sqlConnection + counters_sqlConnection))
        return command

    def parse_result(self, dsconfs, result):
        if result.stderr:
            log.debug('MSSQL error: {0}' + ''.join(result.stderr))

        if result.exit_code != 0:
            for dsconf in dsconfs:
                dsconf.params['counter'] = dsconf
            counters = dsconf.params['counter']
            log.info(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return

        # Parse values
        valuemap = {}
        for counterline in filter_sql_stdout(result.stdout):
            key, value = counterline.split(':', 1)
            if key.strip() == 'databasename':
                databasename = value.strip()
                if databasename not in valuemap:
                    valuemap[databasename] = {}
            elif key.strip() == 'ckey':
                _counter = value.strip().lower()
            elif key.strip() == 'cvalue':
                valuemap[databasename][_counter] = value.strip()
            elif key.strip() == 'status':
                valuemap[databasename]['status'] = value.strip()

        for dsconf in dsconfs:
            timestamp = int(time.mktime(time.localtime()))
            databasename = dsconf.params['contexttitle']
            try:
                key = dsconf.params['resource'].lower()
                value = float(valuemap[databasename][key])
                yield dsconf, value, timestamp
            except:
                log.debug("No value was returned for counter {0} on {1}".format(dsconf.params['resource'], databasename))
                if valuemap[databasename].has_key('status'):
                    value = valuemap[databasename]['status']
                    yield dsconf, value, timestamp

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
        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(getSQLAssembly(sqlConnection.version) + sqlConnection.sqlConnection + jobs_sqlConnection))
        return command

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
                'eventClass': '/Status',
                'severity': ZenEventClasses.Error,
                'eventClassKey': 'winrsCollection MSSQLJob',
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
                    'Failed': ZenEventClasses.Critical
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
            except:
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

class PowershellClusterResourceStrategy(object):
    implements(IStrategy)

    key = 'ClusterResource'

    def build_command_line(self, resource, componenttype):
        #Clustering Command opening

        pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

        psClusterCommands = []
        psClusterCommands.append("import-module failoverclusters;")

        clusterappitems = ('$_.Name', '$_.OwnerGroup', '$_.OwnerNode', '$_.State',
            '$_.Description')

        psClusterCommands.append("{0} -name '{1}' " \
            " | foreach {{{2}}};".format(componenttype,
            resource, " + '|' + ".join(clusterappitems)
            ))

        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(psClusterCommands))
        return command

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
            name, ownergroup, ownernode, state, description = stdout
            dsconf0 = dsconfs[0]

            resourceID = 'res-{0}'.format(name)
            compObject = ObjectMap()
            compObject.id = prepId(resourceID)
            compObject.title = name
            compObject.ownernode = ownernode
            compObject.description = description
            compObject.ownergroup = ownergroup
            compObject.state = state
            compObject.compname = dsconf0.params['contextcompname']
            compObject.modname = dsconf0.params['contextmodname']
            compObject.relname = dsconf0.params['contextrelname']

            for dsconf in dsconfs:
                value = (resourceID, state, compObject)
                timestamp = int(time.mktime(time.localtime()))
                yield dsconf, value, timestamp
        else:
            log.debug('Error in parsing cluster resource data')

gsm.registerUtility(PowershellClusterResourceStrategy(), IStrategy, 'powershell Cluster Resources')


class PowershellClusterServiceStrategy(object):
    implements(IStrategy)

    key = 'ClusterService'

    def build_command_line(self, resource, componenttype):
        #Clustering Command opening
        pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

        psClusterCommands = []
        psClusterCommands.append("import-module failoverclusters;")

        clustergroupitems = ('$_.Name', '$_.IsCoreGroup', '$_.OwnerNode', '$_.State',
            '$_.Description', '$_.Id', '$_.Priority')

        psClusterCommands.append("{0} -name '{1}' " \
            " | foreach {{{2}}};".format(componenttype,
            resource, " + '|' + ".join(clustergroupitems)
            ))

        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(psClusterCommands))
        return command

    def parse_result(self, dsconfs, result):

        if result.exit_code != 0:
            counters = [dsconf.params['resource'] for dsconf in dsconfs]
            log.info(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return
        # Parse values
        stdout = parse_stdout(result, check_stderr=True)
        if stdout:
            name, iscoregroup, ownernode, state, description, nodeid,\
                priority = stdout
            dsconf0 = dsconfs[0]

            compObject = ObjectMap()
            compObject.id = prepId(nodeid)
            compObject.title = name
            compObject.coregroup = iscoregroup
            compObject.ownernode = ownernode
            compObject.state = state
            compObject.description = description
            compObject.priority = priority
            compObject.compname = dsconf0.params['contextcompname']
            compObject.modname = dsconf0.params['contextmodname']
            compObject.relname = dsconf0.params['contextrelname']

            for dsconf in dsconfs:
                value = (name, state, compObject)
                timestamp = int(time.mktime(time.localtime()))
                yield dsconf, value, timestamp
        else:
            log.debug('Error in parsing cluster service data')

gsm.registerUtility(PowershellClusterServiceStrategy(), IStrategy, 'powershell Cluster Services')


class PowershellClusterNodeStrategy(object):
    implements(IStrategy)

    key = 'ClusterNode'

    def build_command_line(self, resource, componenttype):
        psClusterCommands = []
        psClusterCommands.append("import-module failoverclusters;")

        clusternodeitems = pipejoin(
            '$_.Name $_.NodeWeight $_.DynamicWeight $_.Id $_.State'
        )

        psClusterCommands.append("{0} -name '{1}' " \
            " | foreach {{{2}}};".format(componenttype,
            resource, clusternodeitems
            ))

        command = "{0} \"& {{{1}}}\"".format(
            pscommand(),
            ''.join(psClusterCommands))
        return command

    def parse_result(self, dsconfs, result):

        if result.exit_code != 0:
            counters = [dsconf.params['resource'] for dsconf in dsconfs]
            log.info(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return
        # Parse values
        stdout = parse_stdout(result, check_stderr=True)
        if stdout:
            name, node_weight, dynamic_weight, nodeid, state = stdout
            dsconf0 = dsconfs[0]

            nodeID = 'node-{0}'.format(nodeid)
            compObject = ObjectMap()
            compObject.id = prepId(nodeID)
            compObject.title = name
            compObject.ownernode = name
            compObject.assignedvote = node_weight
            compObject.currentvote = dynamic_weight
            compObject.state = state
            compObject.compname = dsconf0.params['contextcompname']
            compObject.modname = dsconf0.params['contextmodname']
            compObject.relname = dsconf0.params['contextrelname']

            for dsconf in dsconfs:
                value = (name, state, compObject)
                timestamp = int(time.mktime(time.localtime()))
                yield dsconf, value, timestamp
        else:
            log.debug('Error in parsing cluster service data')

gsm.registerUtility(PowershellClusterNodeStrategy(),
    IStrategy, 'powershell Cluster Nodes')


class PowershellClusterDiskStrategy(object):
    implements(IStrategy)

    key = 'ClusterDisk'

    def build_command_line(self, resource, componenttype):
        psClusterCommands = []
        psClusterCommands.append("import-module failoverclusters;")

        clusterdiskitems = pipejoin(
            '$_.Id $_.Name $_.VolumePath $_.OwnerNode $_.DiskNumber '
            '$_.PartitionNumber $_.Size $_.FreeSpace $_.State')

        psClusterCommands.append(
            "$volumeInfo = Get-Disk | Get-Partition | Select DiskNumber, @{"
            "Name='Volume';Expression={Get-Volume -Partition $_ | Select -ExpandProperty ObjectId;}};"
            "$clsSharedVolume = Get-ClusterSharedVolume -errorvariable volumeerr -erroraction 'silentlycontinue'|"
            "where{$_.Name -eq '%s'};"
            "if( -Not $volumeerr){"
            "foreach ($volume in $clsSharedVolume) {"
            "$volumeowner = $volume.OwnerNode.Name;"
            "$csvVolume = $volume.SharedVolumeInfo.Partition.Name;"
            "$csvdisknumber = ($volumeinfo | where { $_.Volume -eq $csvVolume}).Disknumber;"
            "$csvtophysicaldisk = New-Object -TypeName PSObject -Property @{"
                "Id = $csvVolume.substring(11, $csvVolume.length-13);"
                "Name = $volume.Name;"
                "VolumePath = $volume.SharedVolumeInfo.FriendlyVolumeName;"
                "OwnerNode = $volumeowner;"
                "DiskNumber = $csvdisknumber;"
                "PartitionNumber = $volume.SharedVolumeInfo.PartitionNumber;"
                "Size = $volume.SharedVolumeInfo.Partition.Size;"
                "FreeSpace = $volume.SharedVolumeInfo.Partition.Freespace;"
                "State = $volume.State;"
            "}; $csvtophysicaldisk | foreach { %s };};}" % (resource, clusterdiskitems)
            )

        psClusterCommands.append(
            "$diskInfo = Get-Disk | Get-Partition | Select DiskNumber, PartitionNumber,"
            "@{Name='Volume';Expression={Get-Volume -Partition $_ | Select -ExpandProperty ObjectId};},"
            "@{Name='DriveLetter';Expression={Get-Volume -Partition $_ | Select -ExpandProperty DriveLetter};},"
            "@{Name='FileSystemLabel';Expression={Get-Volume -Partition $_ | Select -ExpandProperty FileSystemLabel};},"
            "@{Name='Size';Expression={Get-Volume -Partition $_ | Select -ExpandProperty Size};},"
            "@{Name='SizeRemaining';Expression={Get-Volume -Partition $_ | Select -ExpandProperty SizeRemaining};};"
            "$clsDisk = get-clusterresource -errorvariable diskerr -erroraction 'silentlycontinue'|"
            "where{$_.Name -eq '%s'}| where { $_.ResourceType -eq 'Physical Disk'};"
            "if( -Not $diskerr){"
            "foreach ($disk in $clsDisk) {"
            "$founddisk = $diskInfo | where { $_.FileSystemLabel -eq $disk.Name};"
            "if ($founddisk -ne $null) {"
            "$diskowner = $disk.OwnerNode.Name;"
            "$disknumber = $founddisk.DiskNumber;"
            "$diskpartition = $founddisk.PartitionNumber;"
            "$disksize = $founddisk.Size;"
            "$disksizeremain = $founddisk.SizeRemaining;"
            "$diskvolume = $founddisk.Volume.substring(3);"
            "$physicaldisk = New-Object -TypeName PSObject -Property @{"
            "Id = $diskvolume.substring(8, $diskvolume.length-10);"
            "Name = $disk.Name;VolumePath = $diskvolume;"
            "OwnerNode = $diskowner;DiskNumber = $disknumber;"
            "PartitionNumber = $diskpartition;Size = $disksize;"
            "FreeSpace = $disksizeremain;State = $disk.State;};"
            "$physicaldisk | foreach { %s };};};}" % (resource, clusterdiskitems)
            )

        command = "{0} \"& {{{1}}}\"".format(
            pscommand(),
            ''.join(psClusterCommands))
        return command

    def parse_result(self, dsconfs, result):

        if result.exit_code != 0:
            counters = [dsconf.params['resource'] for dsconf in dsconfs]
            log.info(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return
        # Parse values
        stdout = parse_stdout(result, check_stderr=True)
        if stdout:
            dskid, name, volumepath, ownernode, disknum, \
            partitionnum, size, freespace, state = stdout
            dsconf0 = dsconfs[0]

            compObject = ObjectMap()
            compObject.id = prepId(dskid)
            compObject.title = name
            compObject.volumepath = volumepath
            compObject.ownernode = ownernode
            compObject.disknumber = disknum
            compObject.partitionnumber = partitionnum
            compObject.size = sizeof_fmt(size)
            compObject.freespace = sizeof_fmt(freespace)
            compObject.state = state
            compObject.compname = dsconf0.params['contextcompname']
            compObject.modname = dsconf0.params['contextmodname']
            compObject.relname = dsconf0.params['contextrelname']

            for dsconf in dsconfs:
                value = (name, state, compObject)
                timestamp = int(time.mktime(time.localtime()))
                yield dsconf, value, timestamp
        else:
            log.debug('Error in parsing cluster disk data')

gsm.registerUtility(PowershellClusterDiskStrategy(),
    IStrategy, 'powershell Cluster Disks')


class PowershellClusterNetworkStrategy(object):
    implements(IStrategy)

    key = 'ClusterNetwork'

    def build_command_line(self, resource, componenttype):
        psClusterCommands = []
        psClusterCommands.append("import-module failoverclusters;")

        clusternetworkitems = pipejoin(
            '$_.Id $_.Name $_.Description $_.State'
        )

        psClusterCommands.append("{0} -name '{1}' " \
            " | foreach {{{2}}};".format(componenttype,
            resource, clusternetworkitems
            ))

        command = "{0} \"& {{{1}}}\"".format(
            pscommand(),
            ''.join(psClusterCommands))
        return command

    def parse_result(self, dsconfs, result):

        if result.exit_code != 0:
            counters = [dsconf.params['resource'] for dsconf in dsconfs]
            log.info(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return
        # Parse values
        stdout = parse_stdout(result, check_stderr=True)
        if stdout:
            netid, name, description, state = stdout
            dsconf0 = dsconfs[0]

            compObject = ObjectMap()
            compObject.id = prepId(netid)
            compObject.title = name
            compObject.description = description
            compObject.state = state
            compObject.compname = dsconf0.params['contextcompname']
            compObject.modname = dsconf0.params['contextmodname']
            compObject.relname = dsconf0.params['contextrelname']

            for dsconf in dsconfs:
                value = (name, state, compObject)
                timestamp = int(time.mktime(time.localtime()))
                yield dsconf, value, timestamp
        else:
            log.debug('Error in parsing cluster network data')

gsm.registerUtility(PowershellClusterNetworkStrategy(),
    IStrategy, 'powershell Cluster Network')


class PowershellClusterInterfaceStrategy(object):
    implements(IStrategy)

    key = 'ClusterInterface'

    def build_command_line(self, resource, componenttype):
        psClusterCommands = []
        psClusterCommands.append("import-module failoverclusters;")

        clusterinterfaceitems = pipejoin(
                '$_.Id $_.Name $_.Node $_.Network '
                '$_.ipv4addresses $_.Adapter $_.State')

        psClusterCommands.append("{0} -name '{1}' " \
            " | foreach {{{2}}};".format(componenttype,
            resource, clusterinterfaceitems))

        command = "{0} \"& {{{1}}}\"".format(
            pscommand(),
            ''.join(psClusterCommands))
        return command

    def parse_result(self, dsconfs, result):

        if result.exit_code != 0:
            counters = [dsconf.params['resource'] for dsconf in dsconfs]
            log.info(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return
        # Parse values
        stdout = parse_stdout(result, check_stderr=True)
        if stdout:
            intfid, name, node, network, ipaddress, adapter, state = stdout
            dsconf0 = dsconfs[0]

            compObject = ObjectMap()
            compObject.id = prepId(intfid)
            compObject.title = name
            compObject.node = node
            compObject.network = network
            compObject.ipaddresses = ipaddress
            compObject.adapter = adapter
            compObject.state = state
            compObject.compname = dsconf0.params['contextcompname']
            compObject.modname = dsconf0.params['contextmodname']
            compObject.relname = dsconf0.params['contextrelname']

            for dsconf in dsconfs:
                value = (name, state, compObject)
                timestamp = int(time.mktime(time.localtime()))
                yield dsconf, value, timestamp
        else:
            log.debug('Error in parsing cluster Interface data')

gsm.registerUtility(PowershellClusterInterfaceStrategy(),
    IStrategy, 'powershell Cluster Interface')


class PowershellMSSQLInstanceStrategy(object):
    implements(IStrategy)

    key = 'MSSQLInstance'

    def build_command_line(self, instance):
        pscommand = "powershell -NoLogo -NonInteractive " \
            "-OutputFormat TEXT -Command "

        psInstanceCommands = []
        psInstanceCommands.append("$inst = Get-Service -DisplayName 'SQL Server ({0})';".format(instance))
        psInstanceCommands.append("Write-Host $inst.Status'|'$inst.Name;")

        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(psInstanceCommands))
        return command

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
        'cluster_node_server',
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
                    context.instancename)
        elif datasource.strategy == 'powershell MSSQL Instance':
            return (context.device().id,
                    datasource.getCycleTime(context),
                    datasource.strategy,
                    context.instancename,
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
                                        'powershell Cluster Services',
                                        'powershell Cluster Resources',
                                        'powershell Cluster Nodes',
                                        'powershell Cluster Disks',
                                        'powershell Cluster Network',
                                        'powershell Cluster Interface',
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
        if contexttitle == servername and resource == 'get-clustergroup':
            contexttitle = ''

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
                    version=version)

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

    @defer.inlineCallbacks
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
            command_line = strategy.build_command_line(cmd_line_input)
        elif dsconf0.params['strategy'] in ('powershell Cluster Services'
                'powershell Cluster Resources'
                'powershell Cluster Nodes'
                'powershell Cluster Disks'
                'powershell Cluster Network'
                'powershell Cluster Interface'):

            resource = dsconf0.params['contexttitle']
            if not resource:
                return
            componenttype = dsconf0.params['resource']
            command_line = strategy.build_command_line(resource, componenttype)

        elif dsconf0.params['strategy'] == 'Custom Command':
            check_datasource(dsconf0)
            script = dsconf0.params['script']
            usePowershell = dsconf0.params['usePowershell']
            command_line = strategy.build_command_line(script, usePowershell)
        elif dsconf0.params['strategy'] == 'DCDiag':
            testparms = [dsconf.params['script'] for dsconf in config.datasources if dsconf.params['script']]
            command_line = strategy.build_command_line(counters, testparms, dsconf0.windows_user, dsconf0.windows_password)
            conn_info = conn_info._replace(timeout=180)
        else:
            command_line = strategy.build_command_line(counters)

        command = create_single_shot_command(conn_info)
        try:
            results = yield command.run_command(command_line)
        except UnauthorizedError:
            results = ShellResult()
        except Exception, e:
            if "Credentials cache file" in str(e):
                results = ShellResult()
                results.stderr = ['Credentials cache file not found']
            else:
                raise

        defer.returnValue((strategy, config.datasources, results))

    @save
    def onSuccess(self, results, config):
        data = self.new_data()
        dsconf0 = config.datasources[0]
        severity = ZenEventClasses.Clear
        msg = 'winrs: successful collection'

        if not results:
            return data

        strategy, dsconfs, result = results
        if strategy.key == 'CustomCommand':
            cmdResult = strategy.parse_result(config, result)
            data['events'] = cmdResult.events
            if result.exit_code == 0:
                dsconf = dsconfs[0]
                for dp, value in cmdResult.values:
                    data['values'][dsconf.component][dp.id] = value, 'N'
            else:
                msg = 'No output from script for {0} on {1}'.format(
                    dsconf0.datasource, config)
                log.warn(msg)
                severity = ZenEventClasses.Warning
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
                    'Stopped': ZenEventClasses.Critical
                }.get(value[1], ZenEventClasses.Info)

                summary = 'MSSQL Instance {0} is {1}.'.format(
                        dsconf.component,
                        value[1].strip()
                    )

                data['events'].append(dict(
                    eventClass='/Status',
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
                db_statuses = {}
                for dsconf, value, timestamp in strategy.parse_result(dsconfs, result):
                    checked_result = True
                    if dsconf.datasource == 'state':
                        try:
                            state = value[1]
                        except (IndexError, Exception):
                            continue
                        currentstate = {
                            'Online': ZenEventClasses.Clear,
                            'Offline': ZenEventClasses.Critical,
                            'PartialOnline': ZenEventClasses.Error,
                            'Failed': ZenEventClasses.Critical
                        }.get(state, ZenEventClasses.Info)

                        data['events'].append(dict(
                            eventClass=dsconf.eventClass or "/Status",
                            eventClassKey='winrs{0}'.format(strategy.key),
                            eventKey=strategy.key,
                            severity=currentstate,
                            summary='Last state of component was {0}'.format(state),
                            device=config.id,
                            component=prepId(dsconf.component)
                        ))

                        data['values'][dsconf.component]['state'] = cluster_state_value(state), timestamp
                    else:
                        if value == 'offline' and strategy.key == 'PowershellMSSQL':
                            db_statuses[dsconf.component] = False
                        else:
                            data['values'][dsconf.component][dsconf.datasource] = value, timestamp
                            if strategy.key == 'PowershellMSSQL':
                                db_statuses[dsconf.component] = True
                for db in db_statuses:
                    dsconf = get_dsconf(dsconfs, db)
                    if not dsconf:
                        continue

                    dbstatus = 1 if db_statuses[db] else 0
                    data['values'][dsconf.component]['status'] = dbstatus

                    summary='Database {0} is {1}.'.format(dsconf.params['contexttitle'], 'Accessible' if db_statuses[db] else 'Inaccessible')
                    data['events'].append(dict(
                        eventClass=dsconf.eventClass or "/Status",
                        eventClassKey='winrsCollection'.format(strategy.key),
                        eventKey=strategy.key,
                        severity=ZenEventClasses.Clear if db_statuses[db] else dsconf.severity,
                        device=config.id,
                        summary=summary,
                        component=prepId(db)
                    ))
                if not checked_result:
                    msg = 'Error parsing data in {0} strategy for "{1}"'\
                        ' datasource'.format(
                            dsconf0.params['strategy'],
                            dsconf0.datasource,
                        )
                    severity = ZenEventClasses.Warning

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
            eventClass='/Status',
            severity=ZenEventClasses.Clear,
            eventClassKey='winrsCollectionError',
            eventKey='winrsCollection',
            summary='Monitoring ok',
            device=config.id))

        generateClearAuthEvents(config, data['events'])

        return data

    @save
    def onError(self, result, config):
        logg = log.error
        msg, event_class = check_for_network_error(result, config)
        eventKey = 'winrsCollection'
        if isinstance(result, Failure):
            if isinstance(result.value, WindowsShellException):
                result = str(result.value)
                eventKey = 'datasourceWarning_{0}'.format(
                    config.datasources[0].datasource
                )
                msg = '{0} on {1}'.format(result, config)
                logg = log.warn
            elif isinstance(result.value, RequestError):
                args = result.value.args
                msg = args[0] if args else format_exc(result.value)
                event_class = '/Status'

        logg(msg)
        data = self.new_data()
        errorMsgCheck(config, data['events'], result.value.message)
        if not data['events']:
            data['events'].append(dict(
                eventClass=event_class,
                severity=ZenEventClasses.Warning,
                eventClassKey='winrsCollectionError',
                eventKey=eventKey,
                summary='WinRS: ' + msg,
                device=config.id))
        return data


def get_dsconf(dsconfs, component):
    for dsconf in dsconfs:
        if component == dsconf.component:
            return dsconf


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
    except:
        script = ''
        log.error('Invalid tales expression in custom command script: %s' % \
                  str(datasource.script))
    return script
