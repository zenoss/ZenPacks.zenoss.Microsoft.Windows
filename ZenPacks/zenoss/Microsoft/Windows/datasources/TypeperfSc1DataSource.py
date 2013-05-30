##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses WinRS to run typeperf -sc1.

See Products.ZenModel.ZenPack._getClassesByPath() to understand how this class
gets discovered as a datasource type in Zenoss.
"""

import csv
import time
import logging
import calendar
from zope.component import adapts
from zope.interface import implements
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
TYPEPERFSC1_SOURCETYPE = 'WinRS typeperf -sc1'


class SingleCounterDataSource(PythonDataSource):
    """
    Subclass PythonDataSource to put a
    new datasources into Zenoss
    Base datasource for TypeperfSc1DataSource and
    PowershellGetCounterDataSource
    """

    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = 300
    counter = ''
    _properties = PythonDataSource._properties + (
        {'id': 'counter', 'type': 'string'},)


class TypeperfSc1DataSource(SingleCounterDataSource):
    """
    Datasource used to capture datapoints from winrs typeperf -sc1.
    """

    sourcetypes = (TYPEPERFSC1_SOURCETYPE,)
    sourcetype = sourcetypes[0]
    plugin_classname = ZENPACKID + \
        '.datasources.TypeperfSc1DataSource.TypeperfSc1Plugin'


class ITypeperfSc1Info(IRRDDataSourceInfo):
    """
    Provide the UI information for the WinRS typeperf -sc1 datasource.
    """

    counter = schema.TextLine(
        group=_t(TYPEPERFSC1_SOURCETYPE),
        title=_t('Counter'))


class SingleCounterInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the WinRS typeperf -sc1
    plugin.
    """
    implements(ITypeperfSc1Info)
    adapts(TypeperfSc1DataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    counter = ProxyProperty('counter')


class SingleCounterPlugin(PythonDataSourcePlugin):

    proxy_attributes = ('zWinUser', 'zWinPassword')

    @classmethod
    def config_key(cls, datasource, context):
        """
        Uniquely pull in datasources
        """
        return (context.device().id,
                datasource.getCycleTime(context),
                datasource.counter)

    @classmethod
    def params(cls, datasource, context):
        return dict(counter=datasource.talesEval(datasource.counter, context))

    @defer.inlineCallbacks
    def collect(self, config):
        scheme = 'http'
        port = 5985
        results = []
        for datasource in config.datasources:
            auth_type = 'basic'
            if '@' in datasource.zWinUser:
                auth_type = 'kerberos'
            conn_info = ConnectionInfo(
                datasource.manageIp,
                auth_type,
                datasource.zWinUser,
                datasource.zWinPassword,
                scheme,
                port)
            cmd = create_single_shot_command(conn_info)
            command_line = self._build_command_line(
                datasource.params['counter'])
            result = yield cmd.run_command(command_line)
            results.append((datasource, result))
        defer.returnValue(results)

    def onSuccess(self, results, config):
        data = self.new_data()
        self._parse_results(results, data)
        data['events'].append(dict(
            eventClassKey='typeperfCollectionSuccess',
            eventKey='typeperfCollection',
            summary='typeperf: successful collection',
            device=config.id))
        return data

    def onError(self, result, config):
        msg = 'typeperf: failed collection {0} {1}'.format(result, config)
        log.error(msg)
        data = self.new_data()
        data['events'].append(dict(
            eventClassKey='typeperfCollectionError',
            eventKey='typeperfCollection',
            summary=msg,
            device=config.id))
        return data


class TypeperfSc1Plugin(SingleCounterPlugin):

    def _build_command_line(self, counter):
        return 'typeperf "{0}" -sc 1'.format(counter)

    def _parse_results(self, results, data):
        for ds, result in results:
            if result.exit_code != 0:
                log.info('Non-zero exit code ({0}) for counter, {1}, on {2}'
                         .format(
                         result.exit_code, ds.params['counter'], ds.device))
                continue
            rows = list(csv.reader(result.stdout))
            timestamp_str, value_str = rows[1]
            format = '%m/%d/%Y %H:%M:%S.%f'
            timestamp = calendar.timegm(time.strptime(timestamp_str, format))
            value = float(value_str)
            data['values'][ds.component][ds.datasource] = (value, timestamp)
