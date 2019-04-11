##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses WinRS to collect Windows Service Status

"""
import logging
import time
import re

from zope.component import adapts
from zope.interface import implements
from zope.schema.vocabulary import SimpleVocabulary
from twisted.internet import defer, error
from twisted.python.failure import Failure
from Products.Zuul.infos import InfoBase
from Products.Zuul.interfaces import ICatalogTool, IInfo
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.Zuul.utils import severityId
from Products.ZenEvents import ZenEventClasses
from Products.ZenUtils.Utils import prepId
from Products.ZenRRD.zencommand import DataPointConfig
from Products.AdvancedQuery import MatchRegexp

from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin

from ..WinService import WinService

from ..jobs import ReindexWinServices
from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
from ..utils import errorMsgCheck, generateClearAuthEvents, get_dummy_dpconfig
from . import send_to_debug

# Requires that txwinrm_utils is already imported.
from txwinrm.collect import create_enum_info
from txwinrm.WinRMClient import EnumerateClient
from ..txcoroutine import coroutine

log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'

STATE_RUNNING = 'Running'
STATE_STOPPED = 'Stopped'
STATE_RUNNING_PAUSED = 'Running, Paused'
STATE_STOPPED_PAUSED = 'Stopped, Paused'
STATE_PAUSED = 'Paused'

MODE_NONE = 'None'
MODE_AUTO = 'Auto'
MODE_DISABLED = 'Disabled'
MODE_MANUAL = 'Manual'
MODE_ANY = 'Any'
INVALID_REGEX = 'Ignoring invalid regular expression found in WinService datasource {}: {}'


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
    servicename = '${here/id}'
    alertifnot = 'Running'
    startmode = ''
    in_exclusions = '+.*'
    reindex = False

    plugin_classname = ZENPACKID + \
        '.datasources.ServiceDataSource.ServicePlugin'

    _properties = PythonDataSource._properties + (
        {'id': 'servicename', 'type': 'string'},
        {'id': 'alertifnot', 'type': 'string'},
        {'id': 'startmode', 'type': 'string'},
        {'id': 'in_exclusions', 'type': 'string'},
        {'id': 'reindex', 'type': 'boolean'}
    )

    def getAffectedServices(self):
        """Generate WinService instances to which this datasource is bound."""
        template = self.rrdTemplate().primaryAq()
        deviceclass = template.deviceClass()
        # Template is local to a specific service.
        if deviceclass is None:
            yield template.getPrimaryParent()

        # Template is in a device class.
        else:
            query = None
            # Let's be smart and get only what will be affected
            if template.id == 'WinService':
                for exp in self.in_exclusions.split(','):
                    regex = exp.strip().lstrip('+-')
                    try:
                        re.compile(regex)
                    except re.error:
                        log.debug(INVALID_REGEX.format(self.id, regex))
                        continue
                    if not query:
                        query = MatchRegexp('id', regex)
                    else:
                        query |= MatchRegexp('id', regex)
                # this should not occur, but just in case
                if not query:
                    query = MatchRegexp('id', '.*')
            else:
                # component template for specific service
                query = MatchRegexp('id', template.id)
            results = ICatalogTool(deviceclass.primaryAq()).search(WinService, query=query)
            for result in results:
                try:
                    service = result.getObject()
                except Exception:
                    continue

                if service.getRRDTemplate() == template:
                    yield service


class IServiceDataSourceInfo(IInfo):
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

    severity = schema.TextLine(title=_t(u'Severity'),
                               xtype='severity')

    reindex = schema.Bool(
        title=_t('Update services immediately.  This could take several minutes to complete.'))

    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    alertifnot = schema.Choice(
        group=_t('Service Status'),
        title=_t('Alert if service is NOT in this state'),
        vocabulary=SimpleVocabulary.fromValues(
            [STATE_RUNNING, STATE_STOPPED, STATE_RUNNING_PAUSED, STATE_STOPPED_PAUSED]),)

    startmode = schema.Text(
        group=_t('Service Options'),
        xtype='startmodegroup')

    in_exclusions = schema.TextLine(
        group=_t('Service Options'),
        title=_t('Inclusions(+)/Exclusions(-) separated by commas.  Regex accepted'))


class ServiceDataSourceInfo(InfoBase):
    """
    Pull in proxy values so they can be utilized
    within the WinRS Service plugin.
    """
    implements(IServiceDataSourceInfo)
    adapts(ServiceDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    reindex = ProxyProperty('reindex')
    enabled = ProxyProperty('enabled')
    alertifnot = ProxyProperty('alertifnot')
    startmode = ProxyProperty('startmode')
    in_exclusions = ProxyProperty('in_exclusions')

    @property
    def type(self):
        return self._object.sourcetype

    @property
    def newId(self):
        return self._object.id

    def set_severity(self, value):
        try:
            if isinstance(value, str):
                value = severityId(value)
        except ValueError:
            # they entered junk somehow (default to info if invalid)
            value = severityId('info')
        self._object.severity = value

    def get_severity(self):
        return self._object.severity

    def post_update(self):
        if self.reindex:
            for job in self._object.getDmdRoot('Devices').JobManager.getPendingJobs():
                if job.type == ReindexWinServices.getJobType():
                    log.info('ServiceDataSource: ReindexWinServices already pending')
                    self.reindex = False
                    return
            self._object.dmd.JobManager.addJob(ReindexWinServices,
                                               kwargs=dict(uid=self.uid))
            self.reindex = False

    severity = property(get_severity, set_severity)


class ServicePlugin(PythonDataSourcePlugin):
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

        params['servicename'] = datasource.talesEval(
            datasource.servicename, context)
        try:
            params['alertifnot'] = context.alertifnot
        except AttributeError:
            # Use 'Running' by default
            params['alertifnot'] = 'Running'
        try:
            params['severity'] = context.failSeverity
        except AttributeError:
            # Use Error by default
            params['severity'] = ZenEventClasses.Error

        params['rrdpath'] = context.rrdPath() + '/'
        if hasattr(context, 'getMetricMetadata'):
            params['metricmetadata'] = context.getMetricMetadata()

        return params

    def __init__(self, config=None):
        """Initialize plugin. Executed when task is created."""
        # Add a "state_state" datapoint to every datasource. This corresponds
        # to the built-in datasource in the WinService monitoring template.
        for datasource in getattr(config, 'datasources', []):
            dp = DataPointConfig()
            dp.component = getattr(datasource, 'component', None)
            dp.rrdPath = datasource.params.get('rrdpath', None)
            dp.metadata = datasource.params.get('metricmetadata', None)
            datasource.points.append(get_dummy_dpconfig(dp, 'state'))

    @coroutine
    def collect(self, config):

        log.debug('{0}:Start Collection of Services'.format(config.id))

        WinRMQueries = [
            create_enum_info(
                'select name, state, status, displayname from Win32_Service'
            )
        ]

        conn_info = createConnectionInfo(config.datasources[0])

        winrm = EnumerateClient(conn_info)
        try:
            results = yield winrm.do_collect(WinRMQueries)
        except Exception as e:
            if 'referenced context has expired' in e.message:
                results = yield winrm.do_collect(WinRMQueries)
            else:
                raise

        defer.returnValue(results)

    def buildServicesDict(self, datasources):
        services = {}
        for ds in datasources:
            services[ds.params['servicename']] = {'severity': ds.params['severity'],
                                                  'alertifnot': ds.params['alertifnot']}
        return services

    def onSuccess(self, results, config):
        '''
        Examples:
            {   'DisplayName': 'Wired AutoConfig',
                'Name': 'dot3svc',
                'State': 'Stopped',
                'Status': 'OK'},
            {   'DisplayName': 'Diagnostic Policy Service',
                'Name': 'DPS',
                'State': 'Running',
                'Status': 'OK'}
        '''
        data = self.new_data()
        log.debug('{}: Windows services query results: {}'.format(config.id, results))
        try:
            serviceinfo = results[results.keys()[0]]
        except Exception:
            data['events'].append({
                'severity': ZenEventClasses.Error,
                'eventClassKey': 'WindowsServiceCollectionStatus',
                'eventKey': 'WindowsServiceCollection',
                'summary': 'No or bad results returned for service query',
                'device': config.id})
            return data

        # build dictionary of datasource service info
        services = self.buildServicesDict(config.datasources)
        timestamp = int(time.mktime(time.localtime()))
        for index, svc_info in enumerate(serviceinfo):
            svc_info_name = prepId(svc_info.Name)
            if svc_info_name not in services.keys():
                continue

            severity = ZenEventClasses.Clear
            service = services[svc_info_name]

            if svc_info.State not in [alertifnot.strip() for alertifnot in service['alertifnot'].split(',')]:
                evtmsg = 'Service Alert: {0} has changed to {1} state'.format(
                    svc_info.Name,
                    svc_info.State
                )
                severity = service['severity']
            else:
                evtmsg = 'Service Recovered: {0} has changed to {1} state'.format(
                    svc_info.Name,
                    svc_info.State
                )

            if svc_info.State.lower() == STATE_RUNNING.lower():
                data['values'][svc_info_name]['state'] = (0, timestamp)
            elif svc_info.State.lower() == STATE_STOPPED.lower():
                data['values'][svc_info_name]['state'] = (1, timestamp)
            elif svc_info.State.lower() == STATE_PAUSED.lower():
                data['values'][svc_info_name]['state'] = (2, timestamp)

            # event for the service
            data['events'].append({
                'service_name': svc_info_name,
                'service_state': svc_info.State,
                'service_status': svc_info.Status,
                'eventClass': "/Status/WinService",
                'eventKey': "WindowsService",
                'severity': severity,
                'summary': evtmsg,
                'component': svc_info_name,
                'device': config.id,
            })

        # Event to provide notification that check has completed
        data['events'].append({
            'device': config.id,
            'summary': 'Windows Service Check: successful service collection',
            'severity': ZenEventClasses.Clear,
            'eventKey': 'WindowsServiceCollection',
            'eventClass': '/Status'
        })

        generateClearAuthEvents(config, data['events'])

        return data

    def onError(self, result, config):
        prefix = 'failed collection - '
        if isinstance(result, Failure):
            result = result.value
            if isinstance(result, error.TimeoutError):
                result.message = 'Timeout while connecting to host {}'.format(config.id)
                prefix = ''
        msg = 'WindowsServiceLog: {0}{1} {2}'.format(prefix, result, config)
        logg = log.error
        if send_to_debug(result):
            logg = log.debug
        logg(msg)
        data = self.new_data()
        if not errorMsgCheck(config, data['events'], result.message):
            data['events'].append({
                'severity': ZenEventClasses.Error,
                'eventClass': '/Status',
                'eventKey': 'WindowsServiceCollection',
                'summary': msg,
                'device': config.id})
        return data
