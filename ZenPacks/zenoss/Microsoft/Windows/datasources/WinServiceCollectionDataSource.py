##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses WinRS to collect Windows Event Logs

"""
import logging

from zope.component import adapts
from zope.interface import implements
from Products.Zuul.infos.template import RRDDataSourceInfo
from Products.Zuul.interfaces import IRRDDataSourceInfo
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.ZenEvents import ZenEventClasses
from Products.ZenUtils.Utils import prepId

from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin

from ZenPacks.zenoss.Microsoft.Windows.utils \
    import addLocalLibPath

addLocalLibPath()

from txwinrm.collect \
    import ConnectionInfo, WinrmCollectClient, create_enum_info


log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'

subscriptions_dct = {}


def string_to_lines(string):
    if isinstance(string, (list, tuple)):
        return string
    elif hasattr(string, 'splitlines'):
        return string.splitlines()

    return None


class WinServiceCollectionDataSource(PythonDataSource):
    """
    Subclass PythonDataSource to put a new datasources into Zenoss
    """

    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = 300
    counter = ''
    strategy = ''
    sourcetypes = ('WinServices',)
    sourcetype = sourcetypes[0]
    servicename = ''
    alertifnot = ''

    plugin_classname = ZENPACKID + \
        '.datasources.WinServiceCollectionDataSource.WinServiceCollectionPlugin'

    _properties = PythonDataSource._properties + (
        {'id': 'servicename', 'type': 'string'},
        {'id': 'alertifnot', 'type': 'string'},
        )


class IWinServiceCollectionInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the WinRS Single Counter datasource.
    """
    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    servicename = schema.TextLine(
        group=_t('Service Status'),
        title=_t('Service Name'))

    alertifnot = schema.Text(
        group=_t(u'Service Status'),
        title=_t('Alert if not'))


class WinServiceCollectionInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the WinRS Single
    Counter plugin.
    """
    implements(IWinServiceCollectionInfo)
    adapts(WinServiceCollectionDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    servicename = ProxyProperty('servicename')
    alertifnot = ProxyProperty('alertifnot')


class WinServiceCollectionPlugin(PythonDataSourcePlugin):
    proxy_attributes = (
        'zWinUser',
        'zWinPassword',
        )

    @classmethod
    def config_key(cls, datasource, context):
        params = cls.params(datasource, context)
        return(
            context.device().id,
            datasource.getCycleTime(context),
            datasource.id,
            datasource.plugin_classname,
            params.get('servicename'),
            params.get('alertifnot'),
            )

    @classmethod
    def params(cls, datasource, context):
        params = {}

        params['servicename'] = datasource.talesEval(
            datasource.servicename, context)

        params['alertifnot'] = datasource.talesEval(
            datasource.alertifnot, context)

        return params

    def collect(self, config):

        log.info('{0}:Start Collection of Services'.format(config.id))

        scheme = 'http'
        port = 5985
        auth_type = 'basic'

        ds0 = config.datasources[0]

        servicename = ds0.params['servicename']

        WinRMQueries = [
            create_enum_info('select name, state, status, displayname'\
             ' from Win32_Service where name = "{0}"'.format(servicename))]

        conn_info = ConnectionInfo(
            ds0.manageIp,
            auth_type,
            ds0.zWinUser,
            ds0.zWinPassword,
            scheme,
            port)
        winrm = WinrmCollectClient()
        results = winrm.do_collect(conn_info, WinRMQueries)

        return results

    def onSuccess(self, results, config):
        data = self.new_data()
        ds0 = config.datasources[0]
        serviceinfo = results[results.keys()[0]]

        if serviceinfo[0].State != ds0.params['alertifnot']:

            evtmessage = 'Service Alert: {0} has changed to {1} state'.format(
                        serviceinfo[0].Name,
                        serviceinfo[0].State)

            data['events'].append({
                    'eventClassKey': 'WindowsServiceLog',
                    'eventKey': 'WindowsService',
                    'severity': ZenEventClasses.Critical,
                    'summary': evtmessage,
                    'component': prepId(serviceinfo[0].Name),
                    'device': config.id,
                    })
        else:

            evtmessage = 'Service Recoverd: {0} has changed to {1} state'.format(
                        serviceinfo[0].Name,
                        serviceinfo[0].State)

            data['events'].append({
                    'eventClassKey': 'WindowsServiceLog',
                    'eventKey': 'WindowsService',
                    'severity': ZenEventClasses.Clear,
                    'summary': evtmessage,
                    'component': prepId(serviceinfo[0].Name),
                    'device': config.id,
                    })

        data['events'].append({
            'device': config.id,
            'summary': 'Windows Service Check: successful service collection',
            'severity': ZenEventClasses.Info,
            'eventKey': 'WindowsServiceCollection',
            'eventClassKey': 'WindowsServiceLogSuccess',
            })

        return data

    def onError(self, result, config):
        msg = 'WindowsServiceLog: failed collection {0} {1}'.format(result, config)
        log.error(msg)
        data = self.new_data()
        data['events'].append({
            'severity': ZenEventClasses.Warning,
            'eventClassKey': 'WindowsServiceCollectionError',
            'eventKey': 'WindowsServiceCollection',
            'summary': msg,
            'device': config.id})
        return data
