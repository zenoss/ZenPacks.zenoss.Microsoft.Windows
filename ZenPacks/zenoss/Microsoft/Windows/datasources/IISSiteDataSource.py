##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses WinRM to collect Windows IIS Site Status

"""
import logging

from zope.component import adapts
from zope.interface import implements
from twisted.internet import defer
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

from txwinrm.collect \
    import ConnectionInfo, WinrmCollectClient, create_enum_info


log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'

namespace = 'microsoftiisv2'
resource_uri = 'http://schemas.microsoft.com/wbem/wsman/1/wmi/root/{0}/*'.format(
    namespace)


def string_to_lines(string):
    if isinstance(string, (list, tuple)):
        return string
    elif hasattr(string, 'splitlines'):
        return string.splitlines()

    return None


class IISSiteDataSource(PythonDataSource):
    """
    Subclass PythonDataSource to put a new datasources into Zenoss
    """

    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = 300
    sourcetypes = ('Windows IIS Site',)
    sourcetype = sourcetypes[0]
    statusname = '${here/statusname}'

    plugin_classname = ZENPACKID + \
        '.datasources.IISSiteDataSource.IISSiteDataSourcePlugin'

    _properties = PythonDataSource._properties + (
        {'id': 'statusname', 'type': 'string'},
        )


class IIISSiteDataSourceInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the IIS Site datasource.
    """

    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    """statusname = schema.TextLine(
        title=_t('Status Name'))
    """


class IISSiteDataSourceInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the IIS Site plugin.
    """
    implements(IIISSiteDataSourceInfo)
    adapts(IISSiteDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    statusname = ProxyProperty('statusname')


class IISSiteDataSourcePlugin(PythonDataSourcePlugin):
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
            params.get('statusname'),
            )

    @classmethod
    def params(cls, datasource, context):
        params = {}

        params['statusname'] = context.statusname

        return params

    @defer.inlineCallbacks
    def collect(self, config):
        log.debug('{0}:Start Collection of IIS Sites'.format(config.id))
        ds0 = config.datasources[0]
        scheme = ds0.zWinScheme
        port = int(ds0.zWinRMPort)
        auth_type = 'kerberos' if '@' in ds0.zWinRMUser else 'basic'
        connectiontype = 'Keep-Alive'
        keytab = ds0.zWinKeyTabFilePath
        dcip = ds0.zWinKDC

        wql = 'select ServerAutoStart from IIsWebServerSetting where name="{0}"'.format(
            ds0.params['statusname'])

        WinRMQueries = [
            create_enum_info(wql=wql, resource_uri=resource_uri)]

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
        sitestatusinfo = results[results.keys()[0]]

        sitestatus = {'true': 'Running', 'false': 'Stopped'}.get(
            sitestatusinfo[0].ServerAutoStart, 'Unknown')

        evtmessage = 'IIS Service {0} is in {1} state'.format(
            ds0.component,
            sitestatus
            )

        data['events'].append({
            'eventClassKey': 'IISSiteStatus',
            'eventKey': 'IISSite',
            'severity': ZenEventClasses.Info,
            'summary': evtmessage,
            'component': ds0.component,
            'device': config.id,
            })

        return data

    def onError(self, result, config):
        msg = 'WindowsIISSiteLog: failed collection {0} {1}'.format(result, config)
        log.error(msg)
        data = self.new_data()
        data['events'].append({
            'severity': ZenEventClasses.Warning,
            'eventClassKey': 'IISSiteStatusError',
            'eventKey': 'IISSite',
            'summary': msg,
            'device': config.id})
        return data
