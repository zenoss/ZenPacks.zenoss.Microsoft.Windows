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

from twisted.internet import defer

from zope.component import adapts
from zope.interface import implements
from Products.Zuul.infos.template import RRDDataSourceInfo
from Products.Zuul.interfaces import IRRDDataSourceInfo
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.ZenEvents import ZenEventClasses

from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin

from ZenPacks.zenoss.Microsoft.Windows.utils \
    import addLocalLibPath

addLocalLibPath()

from txwinrm.util import ConnectionInfo
from txwinrm.subscribe import create_event_subscription

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

    plugin_classname = ZENPACKID + \
        '.datasources.WinEventCollectionDataSource.WinEventCollectionPlugin'

    _properties = PythonDataSource._properties + (
        {'id': 'eventlog', 'type': 'string'},
        {'id': 'query', 'type': 'lines'},
        )


class IWinServiceCollectionInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the WinRS Single Counter datasource.
    """
    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    eventlog = schema.TextLine(
        group=_t('WindowsEventLog'),
        title=_t('Event Log'))

    query = schema.Text(
        group=_t(u'WindowsEventLog'),
        title=_t('Event Query'),
        xtype='twocolumntextarea')


class WinServiceCollectionInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the WinRS Single
    Counter plugin.
    """
    implements(IWinServiceCollectionInfo)
    adapts(WinServiceCollectionDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    eventlog = ProxyProperty('eventlog')
    query = ProxyProperty('query')


class WinServiceCollectionPlugin(PythonDataSourcePlugin):
    proxy_attributes = (
        'zWinUser',
        'zWinPassword',
        )

    subscriptionID = {}

    @classmethod
    def config_key(cls, datasource, context):
        params = cls.params(datasource, context)
        return(
            context.device().id,
            datasource.getCycleTime(context),
            datasource.id,
            datasource.plugin_classname,
            params.get('eventlog'),
            params.get('query'),
            )

    @classmethod
    def params(cls, datasource, context):
        params = {}

        params['eventlog'] = datasource.talesEval(
            datasource.eventlog, context)

        params['query'] = datasource.talesEval(
            ' '.join(string_to_lines(datasource.query)), context)

        return params

    @defer.inlineCallbacks
    def collect(self, config):
        results = []

        log.info('Start Collection of Services')

        scheme = 'http'
        port = 5985
        auth_type = 'basic'

        ds0 = config.datasources[0]

        conn_info = ConnectionInfo(
            ds0.manageIp,
            auth_type,
            ds0.zWinUser,
            ds0.zWinPassword,
            scheme,
            port)

        path = ds0.params['eventlog']
        select = ds0.params['query']
        try:
            subscription = subscriptions_dct[(ds0.manageIp, path)]
        except:
            subscription = create_event_subscription(conn_info)
            yield subscription.subscribe(path, select)
            subscriptions_dct[(ds0.manageIp, path)] = subscription

        def log_event(event):
            results.append(event)
        yield subscription.pull_once(log_event)

        defer.returnValue(results)

    def onSuccess(self, results, config):
        data = self.new_data()
        for evt in results:

            if evt.rendering_info is not None:
                """
                evt.system.time_created
                evt.system.channel
                evt.system.event_id
                evt.system.provider
                evt.rendering_info.keywords
                evt.rendering_info.message
                """
                errlevel = evt.rendering_info.level

                evtmessage = "EventID: {evtid}\nSource: {evtsource}\nLog: {evtlog}\nMessage: {message}".format(
                    evtid=evt.system.event_id,
                    evtsource=evt.system.provider,
                    evtlog=evt.system.channel,
                    message=evt.rendering_info.message)

                severity = {
                    'Information': ZenEventClasses.Clear,
                    'Warning': ZenEventClasses.Warning,
                    'Error': ZenEventClasses.Critical,
                    }.get(errlevel, ZenEventClasses.Info)

                data['events'].append({
                    'eventClassKey': 'WindowsEventLog',
                    'eventKey': 'WindowsEvent',
                    'severity': severity,
                    'summary': 'Collected Event: %s' % evtmessage,
                    'device': config.id,
                    })

        data['events'].append({
            'device': config.id,
            'summary': 'Windows EventLog: successful event collection',
            'severity': ZenEventClasses.Info,
            'eventKey': 'WindowsEventCollection',
            'eventClassKey': 'WindowsEventLogSuccess',
            })

        return data

    def onError(self, result, config):
        msg = 'WindowsEventLog: failed collection {0} {1}'.format(result, config)
        log.error(msg)
        data = self.new_data()
        data['events'].append({
            'severity': ZenEventClasses.Warning,
            'eventClassKey': 'WindowsEventCollectionError',
            'eventKey': 'WindowsEventCollection',
            'summary': msg,
            'device': config.id})
        return data
