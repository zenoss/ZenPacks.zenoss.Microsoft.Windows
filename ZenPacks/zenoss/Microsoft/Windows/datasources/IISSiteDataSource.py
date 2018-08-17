##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2017, all rights reserved.
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
    check_for_network_error, save, errorMsgCheck, generateClearAuthEvents,
    APP_POOL_STATUSES)

from ..txcoroutine import coroutine

# Requires that txwinrm_utils is already imported.
from txwinrm.collect import create_enum_info
from txwinrm.WinRMClient import SingleCommandClient, EnumerateClient
from . import send_to_debug


log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'

RESOURCE_URI = 'http://schemas.microsoft.com/wbem/wsman/1/wmi/root/{0}/*'
RESOURCE_URI_IIS6 = RESOURCE_URI.format('microsoftiisv2')
RESOURCE_URI_IIS7 = RESOURCE_URI.format('webadministration')


def string_to_lines(string):
    if isinstance(string, (list, tuple)):
        return string
    elif hasattr(string, 'splitlines'):
        return string.splitlines()

    return None


class IISCommander(object):

    def __init__(self, conn_info):
        self.winrs = SingleCommandClient(conn_info)

    PS_COMMAND = "powershell -NoLogo -NonInteractive -NoProfile " \
        "-OutputFormat TEXT -Command "

    IIS_COMMAND = '''
        $iisversion = get-itemproperty HKLM:\SOFTWARE\Microsoft\InetStp\ | select versionstring;
        Write-Host $iisversion.versionstring;
    '''

    def get_app_pool_status(self):
        script = '"& {$Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(4096, 1024);'\
                 ' get-counter \'\APP_POOL_WAS(*)\Current Application Pool State\'}'
        return self.winrs.run_command(self.PS_COMMAND, ps_script=script)

    def get_iis_version(self):
        script = '"& {{{}}}"'.format(
            self.IIS_COMMAND.replace('\n', ' '))
        return self.winrs.run_command(self.PS_COMMAND, ps_script=script)


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
    iis_version = None

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
        return(
            context.device().id,
            datasource.getCycleTime(context),
            datasource.plugin_classname,
        )

    @classmethod
    def params(cls, datasource, context):
        params = {}

        params['statusname'] = context.statusname
        params['iis_version'] = context.iis_version
        params['apppool'] = context.apppool.decode('utf-8').lower()

        return params

    @coroutine
    def collect(self, config):
        log.debug('{0}:Start Collection of IIS Sites'.format(config.id))
        ds0 = config.datasources[0]
        conn_info = createConnectionInfo(ds0)

        wql_iis6 = 'select name, ServerAutoStart from IIsWebServerSetting'.format(
            ds0.params['statusname'])

        wql_iis7 = 'select name, ServerAutoStart from Site'.format(
            ds0.params['statusname'])

        winrm = EnumerateClient(conn_info)
        queries = {create_enum_info(wql=wql_iis6, resource_uri=RESOURCE_URI_IIS6): 'iis6',
                   create_enum_info(wql=wql_iis7, resource_uri=RESOURCE_URI_IIS7): 'iis7'}
        query_results = yield winrm.do_collect(queries.iterkeys())
        winrm_results = {}
        for info, data in query_results.iteritems():
            winrm_results[queries[info]] = data
        log.debug(queries)
        winrs = IISCommander(conn_info)
        winrs_results = yield winrs.get_app_pool_status()
        defer.returnValue((winrm_results, winrs_results))

    @save
    def onSuccess(self, results, config):
        log.debug('IIS Site DataSource results: {}'.format(results))
        data = self.new_data()
        site_results = {}
        try:
            if float(config.datasources[0].params['iis_version']) == 6 or 'iis7' not in results[0]:
                iis_results = results[0]['iis6']
            else:
                iis_results = results[0]['iis7']
        except KeyError:
            log.debug('No results from IIS status query')
        try:
            for result in iis_results:
                site_results[prepId(result.Name)] = result.ServerAutoStart
        except Exception as e:
            log.debug('Error processing IIS site status results: %s', e)
            pass
        app_pool = None
        app_pool_statuses = {}
        try:
            stdout = results[1].stdout
        except Exception:
            stdout = []
        for line in stdout:
            if app_pool is None:
                match = re.match('.*app_pool_was\((.*)\).*', line)
                if match:
                    app_pool = match.group(1)
            else:
                try:
                    app_pool_statuses[app_pool] = int(line)
                except ValueError:
                    # make sure we have an int as the status
                    # we're catching exception below to default to Unknown
                    pass
                app_pool = None

        for ds in config.datasources:
            sitestatusinfo = None
            try:
                sitestatusinfo = site_results[ds.params['statusname']]
            except KeyError:
                try:
                    sitestatusinfo = site_results[prepId(ds.component)]
                except KeyError:
                    pass
            sitestatus = 'Unknown'

            if sitestatusinfo:
                sitestatus = {'true': 'Running', 'false': 'Stopped'}.get(
                    sitestatusinfo, 'Unknown')

            evtmessage = 'IIS Service {0} is in {1} state'.format(
                ds.params['statusname'],
                sitestatus
            )
            data['values'][ds.component]['status'] = {
                'Running': 0,
                'Stopped': 1}.get(sitestatus, -1), 'N'

            if sitestatus == 'Running':
                severity = ZenEventClasses.Clear
            else:
                severity = ds.severity

            if sitestatus == 'Unknown':
                message = 'Ensure that IIS Management Scripts and Tools'

                data['events'].append({
                    'eventClassKey': 'IISSiteStatus',
                    'eventKey': 'IISSite',
                    'severity': severity,
                    'eventClass': ds.eventClass,
                    'summary': evtmessage.decode('UTF-8'),
                    'component': prepId(ds.component),
                    'device': config.id,
                    'message': message,
                })
            else:
                data['events'].append({
                    'eventClassKey': 'IISSiteStatus',
                    'eventKey': 'IISSite',
                    'severity': severity,
                    'eventClass': ds.eventClass,
                    'summary': evtmessage.decode('UTF-8'),
                    'component': prepId(ds.component),
                    'device': config.id,
                })
            try:
                pool_status = app_pool_statuses[ds.params['apppool']]
            except Exception:
                pool_status = -1
            data['values'][ds.component]['appPoolState'] = pool_status, 'N'
            evtmessage = 'Application Pool {} is in {} state'.format(
                ds.params['apppool'], APP_POOL_STATUSES.get(pool_status, 'Unkown'))

            if pool_status == 3:
                severity = ZenEventClasses.Clear
            else:
                severity = ds.severity

            data['events'].append({
                'eventClassKey': 'IISAppPoolStatus',
                'eventKey': 'IISAppPool',
                'severity': severity,
                'eventClass': ds.eventClass,
                'summary': evtmessage.decode('UTF-8'),
                'component': prepId(ds.component),
                'device': config.id
            })

        # Clear previous error event
        data['events'].append({
            'eventClass': '/Status',
            'eventKey': 'IISSite',
            'severity': ZenEventClasses.Clear,
            'summary': 'Monitoring ok',
            'device': config.id,
        })

        generateClearAuthEvents(config, data['events'])

        return data

    def onError(self, result, config):
        msg, event_class = check_for_network_error(
            result, config, default_class='/Status/IIS')
        logg = log.error
        if send_to_debug(result):
            logg = log.debug
        logg("IISSiteDataSource error on %s: %s", config.id, msg)
        data = self.new_data()
        if not errorMsgCheck(config, data['events'], result.value.message):
            generateClearAuthEvents(config, data['events'])
            # only need the one event
            data['events'].append({
                'severity': ZenEventClasses.Warning,
                'eventClass': '/Status',
                'eventKey': 'IISSite',
                'summary': 'IISSite: ' + msg,
                'device': config.id})
        return data
