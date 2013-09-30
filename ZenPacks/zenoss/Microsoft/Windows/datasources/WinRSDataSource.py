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
from xml.etree import cElementTree as ET
from zope.component import adapts
from zope.interface import implements
from zope.schema.vocabulary import SimpleVocabulary
from twisted.internet import defer
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.interfaces import IRRDDataSourceInfo
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.Zuul.utils import safe_hasattr
from Products.Zuul.infos.template import RRDDataSourceInfo
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
    'powershell MSSQL',
    ]

connections_dct = {}


class WinRSDataSource(PythonDataSource):
    """
    Subclass PythonDataSource to put a new datasources into Zenoss
    """

    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = 300
    counter = ''
    strategy = ''

    _properties = PythonDataSource._properties + (
        {'id': 'counter', 'type': 'string'},
        {'id': 'strategy', 'type': 'string'},
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

    counter = schema.TextLine(
        group=_t(WINRS_SOURCETYPE),
        title=_t('Counter'))

    strategy = schema.Choice(
        group=_t(WINRS_SOURCETYPE),
        title=_t('Strategy'),
        vocabulary=SimpleVocabulary.fromValues(
            AVAILABLE_STRATEGIES),)


class WinRSInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the WinRS plugin.
    """
    implements(IWinRSInfo)
    adapts(WinRSDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    counter = ProxyProperty('counter')
    strategy = ProxyProperty('strategy')


class TypeperfSc1Strategy(object):

    def build_command_line(self, counters):
        quoted_counters = ['"{0}"'.format(c) for c in counters]
        counters_args = ' '.join(quoted_counters)
        return 'typeperf {0} -sc 1'.format(counters_args)

    def parse_result(self, dsconfs, result):
        if result.exit_code != 0:
            counters = [dsconf.params['counter'] for dsconf in dsconfs]
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
                key = dsconf.params['counter'].lower()
                value = map_props[key]['value']
                timestamp = map_props[key]['timestamp']
                log.debug('Counter: {0} has value {1}'.format(key, value))
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
            counters = [dsconf.params['counter'] for dsconf in dsconfs]
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
                    key = dsconf.params['counter'].lower()
                    value = map_props[key]['value']
                    timestamp = map_props[key]['timestamp']
                    yield dsconf, value, timestamp
                except (KeyError):
                    log.debug("No value was returned for {0}".format(dsconf.params['counter']))


powershellcounter_strategy = PowershellGetCounterStrategy()


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
                key = dsconf.params['counter'].lower()
                value = float(valuemap[key])
                timestamp = int(time.mktime(time.localtime()))
                yield dsconf, value, timestamp
            except:
                log.debug("No value was returned for {0}".format(dsconf.params['counter']))


powershellmssql_strategy = PowershellMSSQLStrategy()


class WinRSPlugin(PythonDataSourcePlugin):

    proxy_attributes = ('zWinUser',
        'zWinPassword',
        'zWinRMPort',
        'zDBInstances',
        'zDBInstancesPassword',
        )

    @classmethod
    def config_key(cls, datasource, context):
        """
        Uniquely pull in datasources
        """
        return (context.device().id,
                datasource.getCycleTime(context),
                datasource.strategy,
                context.id)

    @classmethod
    def params(cls, datasource, context):
        counter = datasource.talesEval(datasource.counter, context)
        if not counter.startswith('\\') and datasource.strategy != 'powershell MSSQL':
            counter = '\\' + counter
        if safe_hasattr(context, 'perfmonInstance') and context.perfmonInstance is not None:
            counter = context.perfmonInstance + counter

        if safe_hasattr(context, 'instancename'):
            instancename = context.instancename
        else:
            instancename = ''

        databasename = context.title

        servername = context.device().title
        if len(servername) == 0:
            servername = ''

        return dict(counter=counter,
            strategy=datasource.strategy,
            instancename=instancename,
            servername=servername,
            databasename=databasename)

    @defer.inlineCallbacks
    def collect(self, config):
        dsconf0 = config.datasources[0]

        scheme = 'http'
        port = int(dsconf0.zWinRMPort)
        auth_type = 'basic'
        connectiontype = 'Keep-Alive'
        keytab = ''

        if '@' in dsconf0.zWinUser:
            auth_type = 'kerberos'
        conn_info = ConnectionInfo(
            dsconf0.manageIp,
            auth_type,
            dsconf0.zWinUser,
            dsconf0.zWinPassword,
            scheme,
            port,
            connectiontype,
            keytab)

        strategy = self._get_strategy(dsconf0)
        counters = [dsconf.params['counter'] for dsconf in config.datasources]

        if dsconf0.params['strategy'] == 'powershell MSSQL':
            sqlhostname = dsconf0.params['servername']
            dbinstances = dsconf0.zDBInstances
            dbinstancespassword = dsconf0.zDBInstancesPassword

            dblogins = parseDBUserNamePass(dbinstances, dbinstancespassword)
            instance = dsconf0.params['instancename']
            dbname = dsconf0.params['databasename']

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
        for dsconf, value, timestamp in strategy.parse_result(dsconfs, result):
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
        'powershell MSSQL': powershellmssql_strategy,
        'powershell': 'powershell_strategy',
        }.get(dsconf.params['strategy'], 'unknown')
