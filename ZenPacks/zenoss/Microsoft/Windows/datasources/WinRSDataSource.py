##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses WinRS to run typeperf -sc1 or powershell Get-Counter.

See Products.ZenModel.ZenPack._getClassesByPath() to understand how this class
gets discovered as a datasource type in Zenoss.
"""

import csv
import time
import logging
import calendar
import urllib
from urlparse import urlparse


from xml.etree import cElementTree as ET
from zope.component import adapts
from zope.interface import implements
from zope.schema.vocabulary import SimpleVocabulary
from twisted.internet import defer

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

from ZenPacks.zenoss.Microsoft.Windows.utils \
    import addLocalLibPath, parseDBUserNamePass, getSQLAssembly

addLocalLibPath()

from txwinrm.util import ConnectionInfo
from txwinrm.shell import create_long_running_shell, retrieve_long_running_shell

log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
WINRS_SOURCETYPE = 'WinRS'
AVAILABLE_STRATEGIES = [
    'typeperf -sc1',
    'powershell Get-Counter',
    'Custom Command',
    'powershell MSSQL',
    'powershell Cluster Services',
    'powershell Cluster Resources',
    ]

connections_dct = {}


class WinRSDataSource(PythonDataSource):
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
        {'id': 'usePowershell', 'type':'boolean'},
        {'id': 'script', 'type':'string'}
        )
    sourcetypes = (WINRS_SOURCETYPE,)
    sourcetype = sourcetypes[0]
    plugin_classname = ZENPACKID + \
        '.datasources.WinRSDataSource.WinRSPlugin'


class IWinRSInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the WinRS datasource.
    """

    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    strategy = schema.TextLine(
        group=_t(WINRS_SOURCETYPE),
        title=_t('Strategy'),
        xtype='winrsstrategy')

class WinRSInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the WinRS plugin.
    """
    implements(IWinRSInfo)
    adapts(WinRSDataSource)

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

class TypeperfSc1Strategy(object):

    def build_command_line(self, counters):
        quoted_counters = ['"{0}"'.format(c) for c in counters]
        counters_args = ' '.join(quoted_counters)
        return 'typeperf {0} -sc 1'.format(counters_args)

    def parse_result(self, dsconfs, result):
        if result.exit_code != 0:
            counters = [dsconf.params['resource'] for dsconf in dsconfs]
            log.info(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return
        log.debug('Results have been parsed')
        rows = list(csv.reader(result.stdout))
        timestamp_str, milleseconds = rows[1][0].split(".")
        format = '%m/%d/%Y %H:%M:%S'
        timestamp = calendar.timegm(time.strptime(timestamp_str, format))

        map_props = {}
        #Clean out negative numbers from rows returned.
        #Typeperf returns the value as negative but does not return the counter

        for perfvalue_str in rows[1][1:]:
            perfvalue = float(perfvalue_str)
            if perfvalue < 0:
                rows[1].remove(perfvalue_str)

        counterlist = zip(rows[0][1:], rows[1][1:])

        for counter in counterlist:
            arrCounter = counter[0].split("\\")
            countername = "\\{0}\\{1}".format(arrCounter[3], arrCounter[4]).lower()
            value = counter[1]

            map_props.update({countername: {'value': value, 'timestamp': timestamp}})

        for dsconf in dsconfs:
            try:
                key = dsconf.params['resource'].lower()
                value = map_props[key]['value']
                timestamp = map_props[key]['timestamp']
                log.debug('Resource: {0} has value {1}'.format(key, value))
                yield dsconf, value, timestamp
            except (KeyError):
                log.debug("No value was returned for {0}".format(dsconf.params['counter']))

typeperf_strategy = TypeperfSc1Strategy()


class PowershellGetCounterStrategy(object):

    def build_command_line(self, counters):
        quoted_counters = ["'{0}'".format(c) for c in counters]
        counters_args = ', '.join(quoted_counters)
        return "powershell -NoLogo -NonInteractive -NoProfile -OutputFormat " \
               "XML -Command \"get-counter -ea silentlycontinue " \
               "-counter @({0})\"".format(counters_args)

    def parse_result(self, dsconfs, result):
        if result.exit_code != 0 or len(result.stdout) == 0:
            counters = [dsconf.params['resource'] for dsconf in dsconfs]
            log.info(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return

        root_elem = ET.fromstring(result.stdout[1])
        namespace = 'http://schemas.microsoft.com/powershell/2004/04'
        for lst_elem in root_elem.findall('.//{%s}LST' % namespace):
            props_elems = lst_elem.findall('.//{%s}Props' % namespace)

            map_props = {}

            for props_elem in props_elems:
                value = float(props_elem.findtext('./*[@N="CookedValue"]'))
                timestamp = props_elem.findtext('.//*[@N="Timestamp"]')
                path = props_elem.findtext('.//*[@N="Path"]')

                # Confirm timestamp format and convert
                timestamp_str, milleseconds = timestamp.split(".")
                format = '%Y-%m-%dT%H:%M:%S'
                timestamp = calendar.timegm(time.strptime(timestamp_str, format))

                arrPath = path.split("\\")
                indexPath = "\\{0}\\{1}".format(arrPath[3], arrPath[4])

                # System uptime needs to be in centiseconds format
                if 'system up time' in indexPath:
                    value = int(value) * 100

                map_props.update({indexPath: {'value': value, 'timestamp': timestamp}})

            for dsconf in dsconfs:
                try:
                    key = dsconf.params['resource'].lower()
                    value = map_props[key]['value']
                    timestamp = map_props[key]['timestamp']
                    yield dsconf, value, timestamp
                except (KeyError):
                    log.debug("No value was returned for {0}".format(dsconf.params['resource']))


powershellcounter_strategy = PowershellGetCounterStrategy()


class WinParsedResults(ParsedResults):
    """
    WinRS version of ParsedResults. Includes the 'maps' list to automatically apply
    modeling maps.
    """
    def __init__(self):
        self.maps = []
        super(WinParsedResults, self).__init__()


class WinCmdResult(object):
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
    device = ''
    command = None
    ds = ''
    useSsh = False
    cycleTime = None
    env = None
    eventClass = None
    eventKey = None
    lastStart = 0
    lastStop = 0
    points = []
    result = WinCmdResult()
    severity = 3
    usePowershell = False

    
class CustomCommandStrategy(object):
    def build_command_line(self, script, usePowershell):
        pscommand = 'powershell -NoLogo -NonInteractive -NoProfile -OutputFormat TEXT ' \
                    '-Command "%s"' % script
        return pscommand.format(script) if usePowershell else script

    def parse_result(self, dsconfs, result):
        parserLoader = dsconfs[0].params['parser']
        log.debug('Trying to use the %s parser' % parserLoader.pluginName)
        
        # Build emulated Zencommand Cmd object
        cmd = WinCmd()
        cmd.command = dsconfs[0].params['script']
        cmd.ds = dsconfs[0].datasource
        cmd.device = dsconfs[0].params['servername']
        cmd.points = dsconfs[0].points
        cmd.usePowershell = dsconfs[0].params['usePowershell']
        cmd.result.output = '\n'.join(result.stdout)
        cmd.result.exitCode = result.exit_code
        
        collectedResult = WinParsedResults()
        parser = parserLoader.create()
        parser.processResults(cmd, collectedResult)
        return collectedResult

customcommand_strategy = CustomCommandStrategy()

class PowershellMSSQLStrategy(object):

    def build_command_line(self, counters, sqlserver, sqlusername, sqlpassword, database):
        #SQL Command opening

        pscommand = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

        sqlConnection = []
        # Need to modify query where clause.
        # Currently all counters are retrieved for each database

        # DB Connection Object
        sqlConnection.append("$con = new-object " \
            "('Microsoft.SqlServer.Management.Common.ServerConnection')" \
            "'{0}', '{1}', '{2}';".format(sqlserver, sqlusername, sqlpassword))

        sqlConnection.append("$con.Connect();")

        # Connect to Database Server
        sqlConnection.append("$server = new-object " \
            "('Microsoft.SqlServer.Management.Smo.Server') $con;")

        counters_sqlConnection = []

        counters_sqlConnection.append("$query = 'select instance_name as databasename, " \
        "counter_name as ckey, cntr_value as cvalue from " \
        "sys.dm_os_performance_counters where instance_name = '" \
        " + [char]39 + '{0}' + [char]39;".format(
            database
            ))

        """
        # Additional work needs to be done here to limit query

        ) and " \
        "counter_name in ({1})".format(database, counters_args)
        """
        counters_sqlConnection.append("$db = $server.Databases[0];")
        counters_sqlConnection.append("$ds = $db.ExecuteWithResults($query);")
        counters_sqlConnection.append("$ds.Tables | Format-List;")

        command = "{0} \"& {{{1}}}\"".format(
            pscommand,
            ''.join(getSQLAssembly() + sqlConnection + counters_sqlConnection))

        return command

    def parse_result(self, dsconfs, result):

        if result.exit_code != 0:
            counters = [dsconf.params['counter'] for dsconf in dsconfs]
            log.info(
                'Non-zero exit code ({0}) for counters, {1}, on {2}'
                .format(
                    result.exit_code, counters, dsconf.device))
            return

        # Parse values
        valuemap = {}

        for counterline in result.stdout:
            key, value = counterline.split(':')
            if key.strip() == 'ckey':
                _counter = value.strip().lower()
            elif key.strip() == 'cvalue':
                valuemap[_counter] = value.strip()

        for dsconf in dsconfs:
            try:
                key = dsconf.params['resource'].lower()
                value = float(valuemap[key])
                timestamp = int(time.mktime(time.localtime()))
                yield dsconf, value, timestamp
            except:
                log.debug("No value was returned for {0}".format(dsconf.params['resource']))


powershellmssql_strategy = PowershellMSSQLStrategy()


class PowershellClusterResourceStrategy(object):

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
        try:
            for resourceline in result.stdout:
                name, ownergroup, ownernode, state, description = resourceline.split('|')

            dsconf0 = dsconfs[0]

            compObject = ObjectMap()
            compObject.id = prepId(name)
            compObject.title = name
            compObject.ownernode = ownernode
            compObject.description = description
            compObject.ownergroup = ownergroup
            compObject.state = state
            compObject.compname = dsconf0.params['contextcompname']
            compObject.modname = dsconf0.params['contextmodname']
            compObject.relname = dsconf0.params['contextrelname']

            for dsconf in dsconfs:
                try:
                    value = (name, state, compObject)
                    timestamp = int(time.mktime(time.localtime()))
                    yield dsconf, value, timestamp
                except(AttributeError):
                    log.debug("No value was returned for {0}".format(dsconf.params['counter']))
        except(AttributeError):
            log.debug('Error in parsing cluster resource data')

powershellclusterresource_strategy = PowershellClusterResourceStrategy()


class PowershellClusterServiceStrategy(object):

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
        try:
            for resourceline in result.stdout:
                name, iscoregroup, ownernode, state, \
                description, nodeid, priority = resourceline.split('|')

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
                try:
                    value = (name, state, compObject)
                    timestamp = int(time.mktime(time.localtime()))
                    yield dsconf, value, timestamp
                except(AttributeError):
                    log.debug("No value was returned for {0}".format(dsconf.params['counter']))
        except(AttributeError):
            log.debug('Error in parsing cluster service data')

powershellclusterservice_strategy = PowershellClusterServiceStrategy()


class WinRSPlugin(PythonDataSourcePlugin):

    proxy_attributes = (
        'zWinUser',
        'zWinPassword',
        'zWinRMPort',
        'zWinKDC',
        'zWinKeyTabFilePath',
        'zWinScheme',
        'zDBInstances',
        'zDBInstancesPassword',
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
                'Custom Command'):
            resource = '\\' + resource
        if safe_hasattr(context, 'perfmonInstance') and context.perfmonInstance is not None:
            resource = context.perfmonInstance + resource

        if safe_hasattr(context, 'instancename'):
            instancename = context.instancename
        else:
            instancename = ''

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

        return dict(resource=resource,
            strategy=datasource.strategy,
            instancename=instancename,
            servername=servername,
            script=datasource.script,
            parser=parser,
            usePowershell=datasource.usePowershell,
            contextrelname=contextrelname,
            contextcompname=contextcompname,
            contextmodname=contextmodname,
            contexttitle=contexttitle)

    @defer.inlineCallbacks
    def collect(self, config):
        dsconf0 = config.datasources[0]

        scheme = dsconf0.zWinScheme
        port = int(dsconf0.zWinRMPort)
        auth_type = 'kerberos' if '@' in dsconf0.zWinUser else 'basic'
        connectiontype = 'Keep-Alive'
        keytab = dsconf0.zWinKeyTabFilePath
        dcip = dsconf0.zWinKDC

        conn_info = ConnectionInfo(
            dsconf0.manageIp,
            auth_type,
            dsconf0.zWinUser,
            dsconf0.zWinPassword,
            scheme,
            port,
            connectiontype,
            keytab,
            dcip)

        strategy = self._get_strategy(dsconf0)
        counters = [dsconf.params['resource'] for dsconf in config.datasources]

        if dsconf0.params['strategy'] == 'powershell MSSQL':
            sqlhostname = dsconf0.params['servername']
            dbinstances = dsconf0.zDBInstances
            dbinstancespassword = dsconf0.zDBInstancesPassword

            dblogins = parseDBUserNamePass(dbinstances, dbinstancespassword)
            instance = dsconf0.params['instancename']
            dbname = dsconf0.params['contexttitle']

            if instance == 'MSSQLSERVER':
                sqlserver = sqlhostname
            else:
                sqlserver = '{0}\{1}'.format(sqlhostname, instance)

            command_line = strategy.build_command_line(
                counters,
                sqlserver=sqlserver,
                sqlusername=dblogins[instance]['username'],
                sqlpassword=dblogins[instance]['password'],
                database=dbname)

        elif dsconf0.params['strategy'] in ('powershell Cluster Services'
                'powershell Cluster Resources'):

            resource = dsconf0.params['contexttitle']
            componenttype = dsconf0.params['resource']
            command_line = strategy.build_command_line(resource, componenttype)
        
        elif dsconf0.params['strategy'] == 'Custom Command':
            script = dsconf0.params['script']
            usePowershell = dsconf0.params['usePowershell']
            command_line = strategy.build_command_line(script, usePowershell)

        else:
            command_line = strategy.build_command_line(counters)

        try:
            sender = connections_dct[conn_info]['sender']
            shell_id = connections_dct[conn_info]['shell_id']

        except:
            shell_conn = yield create_long_running_shell(conn_info)
            sender = shell_conn['sender']
            shell_id = shell_conn['shell_id']

            connections_dct[conn_info] = {
                'sender': sender,
                'shell_id': shell_id
            }

        try:
            results = yield retrieve_long_running_shell(sender, shell_id, command_line)

        except:
            del connections_dct[conn_info]
            # Shell could have failed for some reason
            # Need to restart shell here
            log.info('Shell ID {0} no longer exists another connection will be \
                created. This could be a result of restarting the client machine \
                or the idle timeout for WinRS is to short. If you are seeing this \
                message freaquently you may need to adjust the idle timeout. \
                Please refer to the FAQ section for information on how to make \
                this adjustment'.format(shell_id))

            shell_conn = yield create_long_running_shell(conn_info)
            sender = shell_conn['sender']
            shell_id = shell_conn['shell_id']

            connections_dct[conn_info] = {
                'sender': sender,
                'shell_id': shell_id
            }

            results = yield retrieve_long_running_shell(sender, shell_id, command_line)

        log.info('Results retreived for device {0} on shell id {1}'.format(
                dsconf0.manageIp,
                shell_id))
        defer.returnValue((strategy, config.datasources, results))

    def onSuccess(self, results, config):
        data = self.new_data()
        strategy, dsconfs, result = results
        
        if 'CustomCommand' in str(strategy.__class__):
            cmdResult = strategy.parse_result(dsconfs, result)
            dsconf = dsconfs[0]
            
            data['events'] = cmdResult.events
            data['maps'] = cmdResult.maps
            for dp, value in cmdResult.values:
                data['values'][dsconf.component][dp] = value, 'N'
        
        else:
            for dsconf, value, timestamp in strategy.parse_result(dsconfs, result):
                if dsconf.datasource == 'state':
                    currentstate = {
                    'Online': ZenEventClasses.Clear,
                    'Offline': ZenEventClasses.Critical,
                    'PartialOnline': ZenEventClasses.Error,
                    'Failed': ZenEventClasses.Critical
                    }.get(value[1], ZenEventClasses.Info)
    
                    data['events'].append(dict(
                        eventClassKey='winrsClusterResource',
                        eventKey='ClusterResource',
                        severity=currentstate,
                        summary='Last state of component was {0}'.format(value[1]),
                        device=config.id,
                        component=prepId(dsconf.component)
                        ))
    
                    data['maps'].append(
                        value[2]
                        )
                else:
                    data['values'][dsconf.component][dsconf.datasource] = value, timestamp

        data['events'].append(dict(
            eventClassKey='winrsCollectionSuccess',
            eventKey='winrsCollection',
            summary='winrs: successful collection',
            device=config.id))
        return data

    def onError(self, result, config):
        msg = 'winrs: failed collection {0} {1}'.format(result, config)
        log.error(msg)
        data = self.new_data()
        data['events'].append(dict(
            eventClassKey='winrsCollectionError',
            eventKey='winrsCollection',
            summary=msg,
            device=config.id))
        return data

    def _get_strategy(self, dsconf):
        return {
        'typeperf -sc1': typeperf_strategy,
        'powershell Get-Counter': powershellcounter_strategy,
        'Custom Command': customcommand_strategy,
        'powershell MSSQL': powershellmssql_strategy,
        'powershell Cluster Services': powershellclusterservice_strategy,
        'powershell Cluster Resources': powershellclusterresource_strategy,
        'powershell': 'powershell_strategy',
        }.get(dsconf.params['strategy'], 'unknown')
