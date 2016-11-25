##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses WinRM to collect Windows IIS Site Status

"""
import logging
import re

from zope.component import adapts
from zope.interface import implements
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

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
from ..utils import (
    check_for_network_error, save, errorMsgCheck, generateClearAuthEvents,)

# Requires that txwinrm_utils is already imported.
from txwinrm.collect import WinrmCollectClient, create_enum_info
from txwinrm.shell import create_single_shot_command


log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'

namespace_iis6 = 'microsoftiisv2'
namespace_iis7 = 'webadministration'
resource_uri_iis6 = 'http://schemas.microsoft.com/wbem/wsman/1/wmi/root/{0}/*'.format(
    namespace_iis6)
resource_uri_iis7 = 'http://schemas.microsoft.com/wbem/wsman/1/wmi/root/{0}/*'.format(
    namespace_iis7)


def string_to_lines(string):
    if isinstance(string, (list, tuple)):
        return string
    elif hasattr(string, 'splitlines'):
        return string.splitlines()

    return None


class IISCommander(object):

    def __init__(self, conn_info):
        self.winrs = create_single_shot_command(conn_info)

    PS_COMMAND = "powershell -NoLogo -NonInteractive -NoProfile " \
        "-OutputFormat TEXT -Command "

    IIS_COMMAND= '''
        $iisversion = get-itemproperty HKLM:\SOFTWARE\Microsoft\InetStp\ | select versionstring;
        Write-Host $iisversion.versionstring;
    '''

    def get_iis_version(self):
        command = '{0} "& {{{1}}}"'.format(
            self.PS_COMMAND, self.IIS_COMMAND.replace('\n', ' '))
        return self.winrs.run_command(command)


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
        {'id': 'iis_version', 'type': 'int'},
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
    proxy_attributes = ConnectionInfoProperties

    @classmethod
    def config_key(cls, datasource, context):
        params = cls.params(datasource, context)
        return(
            context.device().id,
            datasource.getCycleTime(context),
            datasource.id,
            datasource.plugin_classname,
            params.get('statusname'),
            params.get('iis_version'),
        )

    @classmethod
    def params(cls, datasource, context):
        params = {}

        params['statusname'] = context.statusname
        params['iis_version'] = context.iis_version

        return params

    @defer.inlineCallbacks
    def collect(self, config):
        log.debug('{0}:Start Collection of IIS Sites'.format(config.id))
        ds0 = config.datasources[0]
        conn_info = createConnectionInfo(ds0)

        wql_iis6 = 'select ServerAutoStart from IIsWebServerSetting where name="{0}"'.format(
            ds0.params['statusname'])

        wql_iis7 = 'select ServerAutoStart from Site where name="{0}"'.format(
            ds0.params['statusname'])

        iis_version = ds0.params['iis_version']

        if not iis_version:
            winrs = IISCommander(conn_info)
            version = yield winrs.get_iis_version()
            # version should be in 'Version x.x' format
            # 7 and above use the same namespace/query
            try:
                iis_version = re.match('Version (\d).*', version.stdout[0]).group(1)
            except (IndexError, AttributeError):
                if version.stdout:
                    log.error("Malformed version information: {}".format(version.stdout[0]))
                if version.stderr:
                    log.error("Error retrieving IIS Version: {}".format(version.stderr[0]))
                defer.returnValue(None)

        if iis_version == 6:
            WinRMQueries = [create_enum_info(wql=wql_iis6, resource_uri=resource_uri_iis6)]
        else:
            WinRMQueries = [create_enum_info(wql=wql_iis7, resource_uri=resource_uri_iis7)]

        winrm = WinrmCollectClient()
        results = yield winrm.do_collect(conn_info, WinRMQueries)
        log.debug(WinRMQueries)
        defer.returnValue(results)

    @save
    def onSuccess(self, results, config):

        data = self.new_data()
        ds0 = config.datasources[0]
        try:
            sitestatusinfo = results[results.keys()[0]]
        except (IndexError, AttributeError):
            sitestatusinfo = None
        sitestatus = 'Unknown'

        if sitestatusinfo:
            sitestatus = {'true': 'Running', 'false': 'Stopped'}.get(
                sitestatusinfo[0].ServerAutoStart, 'Unknown')

        evtmessage = 'IIS Service {0} is in {1} state'.format(
            ds0.config_key[4],
            sitestatus
        )

        data['events'].append({
            'eventClassKey': 'IISSiteStatus',
            'eventKey': 'IISSite',
            'severity': ZenEventClasses.Info,
            'summary': evtmessage.decode('UTF-8'),
            'component': prepId(ds0.component),
            'device': config.id,
        })

        # Clear previous error event
        data['events'].append({
            'eventClass': '/Status',
            'eventClassKey': 'IISSiteStatusError',
            'eventKey': 'IISSite',
            'severity': ZenEventClasses.Clear,
            'summary': 'Monitoring ok',
            'device': config.id,
        })

        generateClearAuthEvents(config, data['events'])

        return data

    def onError(self, result, config):
        msg, event_class = check_for_network_error(result, config)
        log.error("IISSiteDataSource error on %s: %s", config.id, msg)
        data = self.new_data()
        errorMsgCheck(config, data['events'], result.value.message)
        # only need the one event
        if not data['events']:
            data['events'].append({
                'eventClass': event_class,
                'severity': ZenEventClasses.Warning,
                'eventClassKey': 'IISSiteStatusError',
                'eventKey': 'IISSite',
                'summary': 'IISSite: ' + msg,
                'device': config.id})
        return data
