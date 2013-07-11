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
from Products.ZenUtils.Utils import prepId
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


class WinEventCollectionDataSource(PythonDataSource):
    """
    Subclass PythonDataSource to put a new datasources into Zenoss
    """

    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = 300
    counter = ''
    strategy = ''
    sourcetypes = ('WinEvents',)
    sourcetype = sourcetypes[0]

    plugin_classname = ZENPACKID + \
        '.datasources.WinEventCollectionDataSource.WinEventCollectionPlugin'


class IWinEventCollectionInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the WinRS Single Counter datasource.
    """
    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))


class WinEventCollectionInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the WinRS Single
    Counter plugin.
    """
    implements(IWinEventCollectionInfo)
    adapts(WinEventCollectionDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')


class WinEventCollectionPlugin(PythonDataSourcePlugin):
    proxy_attributes = (
        'zWinUser',
        'zWinPassword',
        'zEventLogs',
        )

    subscriptionID = {}

    @defer.inlineCallbacks
    def collect(self, config):
        data = self.new_data()

        log.info('Start Collection of Events')

        myfile = open('/tmp/events.txt', 'a')
        myfile.write('Start File\n')
        scheme = 'http'
        port = 5985
        auth_type = 'basic'
        #Temp data
        path = 'Application'
        select = '*'

        ds = config.datasources[0]

        conn_info = ConnectionInfo(
            ds.manageIp,
            auth_type,
            ds.zWinUser,
            ds.zWinPassword,
            scheme,
            port)

        try:
            subscription = subscriptions_dct[(ds.manageIp, path)]
        except:
            subscription = create_event_subscription(conn_info)
            yield subscription.subscribe(path, select)
            subscriptions_dct[(ds.manageIp, path)] = subscription

        def log_event(event):
            if event.rendering_info is not None:
                evttime = event.system.time_created
                evtlog = event.system.channel
                evtid = event.system.event_id
                evtsource = event.system.provider
                evtkeyword = event.rendering_info.keywords
                errlevel = event.rendering_info.opcode
                message = event.rendering_info.message
                myfile.write(message)
                log.info(event)

                if 'Info' in errlevel:
                    severity = ZenEventClasses.Clear
                else:
                    severity = ZenEventClasses.Critical

                data['events'].append({
                    'eventClassKey': 'WindowsEventCollection',
                    'eventKey': 'WindowsEventCollection',
                    'severity': severity,
                    'summary': 'Collected Event: %s' % message,
                    'device': config.id,
                    })
                return data

        yield subscription.pull(log_event)

