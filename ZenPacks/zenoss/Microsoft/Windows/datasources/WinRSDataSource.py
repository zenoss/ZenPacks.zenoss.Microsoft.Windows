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
    import addLocalLibPath

addLocalLibPath()

from txwinrm.util import ConnectionInfo
from txwinrm.shell import create_single_shot_command

log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
WINRS_SOURCETYPE = 'WinRS'
TYPEPERF_STRATEGY = 'typeperf -sc1'
POWERSHELL_STRATEGY = 'powershell Get-Counter'


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
        default=TYPEPERF_STRATEGY,
        vocabulary=SimpleVocabulary.fromValues(
            [TYPEPERF_STRATEGY, POWERSHELL_STRATEGY]),)


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
        rows = list(csv.reader(result.stdout))
        timestamp_str = rows[1][0]
        format = '%m/%d/%Y %H:%M:%S.%f'
        timestamp = calendar.timegm(time.strptime(timestamp_str, format))
        for dsconf, value_str in zip(dsconfs, rows[1][1:]):
            value = float(value_str)
            yield dsconf, value, timestamp

typeperf_strategy = TypeperfSc1Strategy()


class PowershellGetCounterStrategy(object):

    def build_command_line(self, counters):
        quoted_counters = ["'{0}'".format(c) for c in counters]
        counters_args = ', '.join(quoted_counters)
        return "powershell -NoLogo -NonInteractive -NoProfile -OutputFormat " \
               "XML -Command \"get-counter -counter @({0})\"".format(counters_args)

    def parse_result(self, dsconfs, result):
        if result.exit_code != 0:
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
            for dsconf, props_elem in zip(dsconfs, props_elems):
                value = float(props_elem.findtext('./*[@N="RawValue"]'))
                # TODO: use timezone information, 2013-05-31T20:47:17.184+00:00
                timestamp_str = props_elem.findtext('.//*[@N="Timestamp"]')[:-7]
                format = '%Y-%m-%dT%H:%M:%S.%f'
                timestamp = calendar.timegm(time.strptime(timestamp_str, format))
                yield dsconf, value, timestamp

powershell_strategy = PowershellGetCounterStrategy()


class WinRSPlugin(PythonDataSourcePlugin):

    proxy_attributes = ('zWinUser', 'zWinPassword')

    @classmethod
    def config_key(cls, datasource, context):
        """
        Uniquely pull in datasources
        """
        return (context.device().id,
                datasource.getCycleTime(context),
                datasource.strategy)

    @classmethod
    def params(cls, datasource, context):
        counter = datasource.talesEval(datasource.counter, context)
        if not counter.startswith('\\'):
            counter = '\\' + counter
        if safe_hasattr(context, 'perfmonInstance') and context.perfmonInstance is not None:
            counter = context.perfmonInstance + counter
        return dict(counter=counter, strategy=datasource.strategy)

    @defer.inlineCallbacks
    def collect(self, config):
        scheme = 'http'
        port = 5985
        auth_type = 'basic'
        dsconf0 = config.datasources[0]
        if '@' in dsconf0.zWinUser:
            auth_type = 'kerberos'
        conn_info = ConnectionInfo(
            dsconf0.manageIp,
            auth_type,
            dsconf0.zWinUser,
            dsconf0.zWinPassword,
            scheme,
            port)
        strategy = self._get_strategy(dsconf0)
        cmd = create_single_shot_command(conn_info)
        counters = [dsconf.params['counter'] for dsconf in config.datasources]
        command_line = strategy.build_command_line(counters)
        result = yield cmd.run_command(command_line)
        defer.returnValue((strategy, config.datasources, result))

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
        if dsconf.params['strategy'] == POWERSHELL_STRATEGY:
            return powershell_strategy
        return typeperf_strategy
