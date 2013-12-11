##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses WinRS to collect Windows Service Status

"""
import logging

from zope.component import adapts
from zope.interface import implements
from zope.schema.vocabulary import SimpleVocabulary
from twisted.internet import defer
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

STATE_RUNNING = 'Running'
STATE_STOPPED = 'Stopped'


def string_to_lines(string):
    if isinstance(string, (list, tuple)):
        return string
    elif hasattr(string, 'splitlines'):
        return string.splitlines()

    return None


class ServiceDataSource(PythonDataSource):
    """
    Subclass PythonDataSource to put a new datasources into Zenoss
    """

    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = 300
    sourcetypes = ('Windows Service',)
    sourcetype = sourcetypes[0]
    servicename = '${here/servicename}'
    alertifnot = 'Running'
    defaultgraph = False

    plugin_classname = ZENPACKID + \
        '.datasources.ServiceDataSource.ServicePlugin'

    _properties = PythonDataSource._properties + (
        {'id': 'servicename', 'type': 'string'},
        {'id': 'alertifnot', 'type': 'string'},
        {'id': 'defaultgraph', 'type': 'boolean', 'mode': 'w'},
        )


class IServiceDataSourceInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the WinRS Service datasource.
    """

    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    servicename = schema.TextLine(
        group=_t('Service Status'),
        title=_t('Service Name'))

    defaultgraph = schema.Bool(
        group=_t('Service Status'),
        title=_t('Monitor by Default')
        )

    alertifnot = schema.Choice(
        group=_t('Service Status'),
        title=_t('Alert if service is NOT in this state'),
        vocabulary=SimpleVocabulary.fromValues(
            [STATE_RUNNING, STATE_STOPPED]),)


class ServiceDataSourceInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the WinRS Service plugin.
    """
    implements(IServiceDataSourceInfo)
    adapts(ServiceDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    servicename = ProxyProperty('servicename')
    alertifnot = ProxyProperty('alertifnot')
    defaultgraph = ProxyProperty('defaultgraph')


class ServicePlugin(PythonDataSourcePlugin):
    proxy_attributes = (
        'zWinRMUser',
        'zWinRMPassword',
        'zWinRMPort',
        'zWinKDC',
        'zWinKeyTabFilePath',
        'zWinScheme',
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

    @defer.inlineCallbacks
    def collect(self, config):

        log.info('{0}:Start Collection of Services'.format(config.id))
        ds0 = config.datasources[0]

        scheme = ds0.zWinScheme
        port = int(ds0.zWinRMPort)
        auth_type = 'kerberos' if '@' in ds0.zWinRMUser else 'basic'
        connectiontype = 'Keep-Alive'
        keytab = ds0.zWinKeyTabFilePath
        dcip = ds0.zWinKDC

        servicename = ds0.params['servicename']

        WinRMQueries = [
            create_enum_info('select name, state, status, displayname'\
             ' from Win32_Service where name = "{0}"'.format(servicename))]

        conn_info = ConnectionInfo(
            ds0.manageIp,
            auth_type,
            ds0.zWinRMUser,
            ds0.zWinRMPassword,
            scheme,
            port,
            connectiontype,
            keytab,
            dcip)
        winrm = WinrmCollectClient()
        results = yield winrm.do_collect(conn_info, WinRMQueries)
        log.debug(WinRMQueries)

        defer.returnValue(results)

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
                    'severity': ds0.severity,
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

        # Event to provide notification that check has completed
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
