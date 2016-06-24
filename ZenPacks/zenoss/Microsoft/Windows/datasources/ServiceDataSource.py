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

from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin

from ..WinService import WinService

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
from ..utils import save, checkExpiredPassword

# Requires that txwinrm_utils is already imported.
from txwinrm.collect import WinrmCollectClient, create_enum_info


log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'

STATE_RUNNING = 'Running'
STATE_STOPPED = 'Stopped'

MODE_NONE = 'None'
MODE_AUTO = 'Auto'
MODE_DISABLED = 'Disabled'
MODE_MANUAL = 'Manual'
MODE_ANY = 'Any'


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

    plugin_classname = ZENPACKID + \
        '.datasources.ServiceDataSource.ServicePlugin'

    _properties = PythonDataSource._properties + (
        {'id': 'servicename', 'type': 'string'},
        {'id': 'alertifnot', 'type': 'string'},
        {'id': 'startmode', 'type': 'string'},
        {'id': 'in_exclusions', 'type': 'string'},
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
            results = ICatalogTool(deviceclass.primaryAq()).search(WinService)
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
    component = schema.TextLine(title=_t(u'Component'))

    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    servicename = schema.TextLine(
        group=_t('Service Status'),
        title=_t('Service Name'))

    alertifnot = schema.Choice(
        group=_t('Service Status'),
        title=_t('Alert if service is NOT in this state'),
        vocabulary=SimpleVocabulary.fromValues(
            [STATE_RUNNING, STATE_STOPPED]),)

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
    servicename = ProxyProperty('servicename')

    def get_enabled(self):
        return self._object.enabled

    def set_enabled(self, value):
        self._object.enabled = value
        for service in self._object.getAffectedServices():
            service.index_object()

    component = ProxyProperty('component')

    def get_alertifnot(self):
        return self._object.alertifnot

    def set_alertifnot(self, value):
        self._object.alertifnot = value
        for service in self._object.getAffectedServices():
            service.index_object()

    def get_startmode(self):
        return self._object.startmode

    def set_startmode(self, value):
        self._object.startmode = value
        for service in self._object.getAffectedServices():
            service.index_object()

    def get_in_exclusions(self):
        return self._object.in_exclusions

    def set_in_exclusions(self, value):
        self._object.in_exclusions = value
        for service in self._object.getAffectedServices():
            service.index_object()

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

    severity = property(get_severity, set_severity)
    enabled = property(get_enabled, set_enabled)

    startmode = property(get_startmode, set_startmode)
    in_exclusions = property(get_in_exclusions, set_in_exclusions)
    alertifnot = property(get_alertifnot, set_alertifnot)


class ServicePlugin(PythonDataSourcePlugin):
    proxy_attributes = ConnectionInfoProperties
    services = {}

    def buildServicesDict(self, datasources):
        '''
            store data about each service and datasource
        '''
        self.services = {}
        for ds in datasources:
            self.services[ds.params['servicename']] = ds.params.get('winservices', {})
        return self.services

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

        params['servicename'] = datasource.talesEval(
            datasource.servicename, context)
        params['usermonitor'] = context.usermonitor
        params['winservices'] = context.get_winservices_modes()

        return params

    @defer.inlineCallbacks
    def collect(self, config):

        ds0 = config.datasources[0]

        # build dictionary of datasource service info
        self.buildServicesDict(config.datasources)

        run_query = False
        for ds in config.datasources:
            id = ds.params['servicename']
            svc_data = self.services.get(id)
            if svc_data.get('manual') or len(svc_data.get('modes',[])) > 0:
                run_query = True
                break

        # no need to run query
        if not run_query:
            log.warn('No startmodes defined in {} and not manually monitored.  Terminating datasource collection.'.format(ds0.datasource))
            defer.returnValue(None)

        log.debug('{0}:Start Collection of Services'.format(config.id))

        WinRMQueries = [
            create_enum_info(
                'select name, state, status, displayname from Win32_Service'
            )
        ]

        conn_info = createConnectionInfo(ds0)

        winrm = WinrmCollectClient()
        results = yield winrm.do_collect(conn_info, WinRMQueries)
        log.debug(WinRMQueries)

        defer.returnValue(results)

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
        params = config.datasources[0].params
        # if monitoring is false, don't monitor
        log.debug('Windows services query results: {}'.format(results))
        try:
            serviceinfo = results[results.keys()[0]]
        except:
            data['events'].append({
                'eventClass': "/Status/WinService",
                'severity': ZenEventClasses.Error,
                'eventClassKey': 'WindowsServiceCollectionStatus',
                'eventKey': 'WindowsServiceCollection',
                'summary': 'No results returned for service query',
                'device': config.id})
            return data

        for index, svc_info in enumerate(serviceinfo):
            svc_id = svc_info.Name
            svc_data = self.services.get(svc_id)
            # skip if this service shouldn't be monitored
            if not svc_data or not svc_data.get('monitor', False):
                log.debug('%s disabled' % svc_id)
                continue

            # continue if this service's state is not in monitored modes
            if svc_data.get('mode') not in svc_data.get('modes', []):
                log.debug('%s mode %s not in modes: %s' % (svc_id, svc_data.get('mode'), svc_data.get('modes', []))) 
                continue

            # if no startmodes, and not manually monitored, skip
            if len(svc_data.get('modes', [])) == 0 and not svc_data.get('manual', False):
                log.debug('No startmodes defined in {} and not manually monitored.  No collection occurred.'
                      .format(config.datasources[0].datasource))
                continue

            severity = ZenEventClasses.Clear

            if svc_info.State != svc_data.get('alertifnot'):
                evtmsg = 'Service Alert: {0} has changed to {1} state'.format(
                    svc_id,
                    svc_info.State
                )
                severity = svc_data.get('severity', 3)
            else:
                evtmsg = 'Service Recovered: {0} has changed to {1} state'.format(
                    svc_info.Name,
                    svc_info.State
                )
            # event for the service
            data['events'].append({
                'component': svc_id,
                'service_name': svc_id,
                'service_state': svc_info.State,
                'service_status': svc_info.Status,
                'eventClass': "/Status/WinService",
                'eventClassKey': 'WindowsServiceLog',
                'eventKey': "WindowsService",
                'severity': severity,
                'summary': evtmsg,
                'component': prepId(svc_id),
                'device': config.id,
            })

        # Event to provide notification that check has completed
        data['events'].append({
            'eventClass': "/Status/WinService",
            'device': config.id,
            'summary': 'Windows Service Check: successful service collection',
            'severity': ZenEventClasses.Clear,
            'eventKey': 'WindowsServiceCollection',
            'eventClassKey': 'WindowsServiceCollectionStatus',
        })
        return data

    def onError(self, result, config):
        prefix = 'failed collection - '
        if isinstance(result, Failure):
            result = result.value
            if isinstance(result, error.TimeoutError):
                result = 'Timeout while connecting to host'
                prefix = ''
        msg = 'WindowsServiceLog: {0}{1} {2}'.format(prefix, result, config)
        log.error(msg)
        data = self.new_data()
        checkExpiredPassword(config, data['events'], result.message)
        if not data['events']:
            data['events'].append({
                'eventClass': "/Status/WinService",
                'severity': ZenEventClasses.Error,
                'eventClassKey': 'WindowsServiceCollectionStatus',
                'eventKey': 'WindowsServiceCollection',
                'summary': msg,
                'device': config.id})
        return data
