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
SINGLE_COUNTER_SOURCETYPE = 'WinRS Single Counter'
TYPEPERF_STRATEGY = 'typeperf -sc1'
POWERSHELL_STRATEGY = 'powershell Get-Counter'


class SingleCounterDataSource(PythonDataSource):
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
    sourcetypes = (SINGLE_COUNTER_SOURCETYPE,)
    sourcetype = sourcetypes[0]
    plugin_classname = ZENPACKID + \
        '.datasources.SingleCounterDataSource.SingleCounterPlugin'


class ISingleCounterInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the WinRS Single Counter datasource.
    """

    counter = schema.TextLine(
        group=_t(SINGLE_COUNTER_SOURCETYPE),
        title=_t('Counter'))

    strategy = schema.Choice(
        group=_t(SINGLE_COUNTER_SOURCETYPE),
        title=_t('Strategy'),
        default=TYPEPERF_STRATEGY,
        vocabulary=SimpleVocabulary.fromValues(
            [TYPEPERF_STRATEGY, POWERSHELL_STRATEGY]),)


class SingleCounterInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the WinRS Single
    Counter plugin.
    """
    implements(ISingleCounterInfo)
    adapts(SingleCounterDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    counter = ProxyProperty('counter')
    strategy = ProxyProperty('strategy')


class TypeperfSc1Strategy(object):

    def build_command_line(self, counter):
        return 'typeperf "{0}" -sc 1'.format(counter)

    def parse_result(self, dsconf, result):
        if result.exit_code != 0:
            log.info(
                'Non-zero exit code ({0}) for counter, {1}, on {2}'
                .format(
                    result.exit_code, dsconf.params['counter'], dsconf.device))
            return None, None
        rows = list(csv.reader(result.stdout))
        timestamp_str, value_str = rows[1]
        format = '%m/%d/%Y %H:%M:%S.%f'
        timestamp = calendar.timegm(time.strptime(timestamp_str, format))
        value = float(value_str)
        return value, timestamp


typeperf_strategy = TypeperfSc1Strategy()


class PowershellGetCounterStrategy(object):

    def build_command_line(self, counter):
        return "powershell -NoLogo -NonInteractive -NoProfile -OutputFormat " \
               "XML -Command \"get-counter -counter '{0}'\"".format(counter)

    def parse_result(self, dsconf, result):
        if result.exit_code != 0:
            log.info(
                'Non-zero exit code ({0}) for counter, {1}, on {2}'
                .format(
                    result.exit_code, dsconf.params['counter'], dsconf.device))
            return None, None
        root_elem = ET.fromstring(result.stdout[1])
        value = float(root_elem.findtext('.//*[@N="RawValue"]'))
        # TODO: use timezone information, 2013-05-31T20:47:17.184+00:00
        timestamp_str = root_elem.findtext('.//*[@N="Timestamp"]')[:-7]
        format = '%Y-%m-%dT%H:%M:%S.%f'
        timestamp = calendar.timegm(time.strptime(timestamp_str, format))
        return value, timestamp


powershell_strategy = PowershellGetCounterStrategy()


class SingleCounterPlugin(PythonDataSourcePlugin):

    proxy_attributes = ('zWinUser', 'zWinPassword')

    @classmethod
    def config_key(cls, datasource, context):
        """
        Uniquely pull in datasources
        """
        return (context.device().id,
                datasource.getCycleTime(context),
                datasource.counter,
                datasource.strategy)

    @classmethod
    def params(cls, datasource, context):
        return dict(counter=datasource.talesEval(datasource.counter, context),
                    strategy=datasource.strategy)

    @defer.inlineCallbacks
    def collect(self, config):
        scheme = 'http'
        port = 5985
        results = []
        for dsconf in config.datasources:
            auth_type = 'basic'
            if '@' in dsconf.zWinUser:
                auth_type = 'kerberos'
            conn_info = ConnectionInfo(
                dsconf.manageIp,
                auth_type,
                dsconf.zWinUser,
                dsconf.zWinPassword,
                scheme,
                port)
            cmd = create_single_shot_command(conn_info)
            command_line = self._get_strategy(dsconf).build_command_line(
                dsconf.params['counter'])
            result = yield cmd.run_command(command_line)
            results.append((dsconf, result))
        defer.returnValue(results)

    def onSuccess(self, results, config):
        data = self.new_data()
        for dsconf, result in results:
            strategy = self._get_strategy(dsconf)
            value, timestamp = strategy.parse_result(dsconf, result)
            if value is None:
                continue
            data['values'][dsconf.component][dsconf.datasource] = \
                value, timestamp
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
