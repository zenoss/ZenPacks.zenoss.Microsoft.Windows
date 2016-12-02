##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2016, all rights reserved.
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
from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin
from Products.Zuul.infos.template import InfoBase
from Products.Zuul.interfaces import IInfo
from Products.Zuul.form import schema
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.Zuul.infos import ProxyProperty
from Products.ZenEvents import ZenEventClasses

from twisted.internet import defer

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
from ..utils import errorMsgCheck, generateClearAuthEvents

# Requires that txwinrm_utils is already imported.
from txwinrm.collect import WinrmCollectClient, create_enum_info

log = logging.getLogger('zen.MicrosoftWindows')
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'


class WinRMPingDataSource(PythonDataSource):
    ZENPACKID = ZENPACKID
    cycletime = '300'
    sourcetypes = ('WinRM Ping',)
    sourcetype = sourcetypes[0]
    enabled = True

    plugin_classname = ZENPACKID + \
        '.datasources.WinRMPingDataSource.WinRMPingDataSourcePlugin'

    _properties = PythonDataSource._properties


class IWinRMPingDataSourceInfo(IInfo):
    """
    Provide the UI information for the WinRS Service datasource.
    """

    newId = schema.TextLine(
        title=_t(u'Name'),
        xtype="idfield",
        description=_t(u'The name of this datasource')
    )
    type = schema.TextLine(
        title=_t(u'Type'),
        readonly=True
    )
    enabled = schema.Bool(
        title=_t(u'Enabled')
    )
    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))


class WinRMPingDataSourceInfo(InfoBase):
    """
    Pull in proxy values so they can be utilized
    within the WinRS Service plugin.
    """
    implements(IWinRMPingDataSourceInfo)
    adapts(WinRMPingDataSource)

    cycletime = ProxyProperty('cycletime')
    enabled = ProxyProperty('enabled')

    @property
    def id(self):
        return '/'.join(self._object.getPrimaryPath())

    @property
    def type(self):
        return self._object.sourcetype

    @property
    def newId(self):
        return self._object.id

    @property
    def source(self):
        return self._object.getDescription()


class WinRMPingDataSourcePlugin(PythonDataSourcePlugin):
    proxy_attributes = ConnectionInfoProperties

    @classmethod
    def config_key(cls, datasource, context):
        return(
            context.device().id,
            datasource.getCycleTime(context),
            datasource.id,
            datasource.plugin_classname,
        )

    @classmethod
    def params(cls, datasource, context):
        params = {}

        return params

    @defer.inlineCallbacks
    def collect(self, config):

        ds0 = config.datasources[0]

        log.debug('{0}:Start WinRM connection test.'.format(config.id))

        conn_info = createConnectionInfo(ds0)

        WinRMQueries = [
            create_enum_info(
                'select * from Win32_OperatingSystem'
            )
        ]

        winrm = WinrmCollectClient()
        results = yield winrm.do_collect(conn_info, WinRMQueries)

        defer.returnValue(results)

    def onSuccess(self, results, config):
        data = self.new_data()
        data['events'].append({
            'eventClass': '/Status/Winrm/Ping',
            'severity': ZenEventClasses.Clear,
            'summary': 'Device is UP!',
            'ipAddress': config.manageIp,
            'device': config.id})

        generateClearAuthEvents(config, data['events'])

        return data

    def onError(self, results, config):
        data = self.new_data()
        log.error('WinRMPing collection: {} on {}'.format(results.value.message, config.id))

        errorMsgCheck(config, data['events'], results.value.message)

        if not data['events']:
            data['events'].append({
                'eventClass': '/Status/Winrm/Ping',
                'severity': ZenEventClasses.Critical,
                'summary': 'Device is DOWN:  {}'.format(results.value.message),
                'ipAddress': config.manageIp,
                'device': config.id})
        return data
