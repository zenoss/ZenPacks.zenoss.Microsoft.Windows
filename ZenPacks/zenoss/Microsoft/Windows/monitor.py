##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from pprint import pformat
from twisted.internet import defer
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.interfaces import IRRDDataSourceInfo
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.Zuul.infos.template import RRDDataSourceInfo
from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin
from .txwinrm.util import ConnectionInfo
from .txwinrm.shell import create_single_shot_command

log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
TYPEPERFSC1_SOURCETYPE = 'WinRS typeperf -sc1'
POWERSHELLGETCOUNTER_SOURCETYPE = 'WinRS powershell Get-Counter'


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


class ITypeperfSc1Info(IRRDDataSourceInfo):
    """
    Provide the UI information for the WinRS typeperf -sc1 datasource.
    """

    counter = schema.TextLine(
        group=_t(TYPEPERFSC1_SOURCETYPE),
        title=_t('Counter'))


class IPowershellGetCounterInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the WinRS powershell Get-Counter datasource.
    """

    counter = schema.TextLine(
        group=_t(POWERSHELLGETCOUNTER_SOURCETYPE),
        title=_t('Counter'))


class SingleCounterInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the WinRS typeperf -sc1
    plugin.
    """

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
        log.warn('BME- SingleCounterPlugin collect {0}'.format(config))
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
        log.warn('BME- SingleCounterPlugin onSuccess {0} {1}'
                 .format(results, config))
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
        log.warn('BME- TypeperfSc1Plugin _build_command_line {0}'
                 .format(counter))
        return 'typeperf "{0}" -sc 1'.format(counter)

    def _parse_results(self, results, data):
        log.warn('BME- TypeperfSc1Plugin _parse_results {0} {1}'
                 .format(pformat(results), pformat(data)))
        for ds, result in results:
            timestamp, value = result.split(',')
            data['values'][ds.component][ds.datasource] = (value, timestamp)
            pass


class PowershellGetCounterPlugin(SingleCounterPlugin):

    def _build_command_line(self, counter):
        log.warn('BME- PowershellGetCounterPlugin _build_command_line {0}'
                 .format(counter))
        return "powershell -NoLogo -NonInteractive -NoProfile -OutputFormat " \
               "XML -Command \"get-counter -counter '{0}'\"".format(counter)

    def _parse_results(self, results, data):
        log.warn('BME- PowershellGetCounterPlugin _parse_results {0} {1}'
                 .format(pformat(results), pformat(data)))
        for datasource, result in results:
            # data['values']
            pass
