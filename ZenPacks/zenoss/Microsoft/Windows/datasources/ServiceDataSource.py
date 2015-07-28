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
from Products.Zuul.infos.template import RRDDataSourceInfo
from Products.Zuul.interfaces import ICatalogTool, IRRDDataSourceInfo
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.ZenEvents import ZenEventClasses
from Products.ZenUtils.Utils import prepId

from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin

from ..WinService import WinService

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo

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
    startmode = MODE_NONE

    plugin_classname = ZENPACKID + \
        '.datasources.ServiceDataSource.ServicePlugin'

    _properties = PythonDataSource._properties + (
        {'id': 'servicename', 'type': 'string'},
        {'id': 'alertifnot', 'type': 'string'},
        {'id': 'startmode', 'type': 'string'},
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


class IServiceDataSourceInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the WinRS Service datasource.
    """

    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    servicename = schema.TextLine(
        group=_t('Service Status'),
        title=_t('Service Name'))

    startmode = schema.Choice(
        group=_t('Service Status'),
        title=_t('Start mode of service to monitor (None disables monitoring)'),
        vocabulary=SimpleVocabulary.fromValues(
            [MODE_NONE,MODE_ANY,MODE_AUTO,MODE_DISABLED,MODE_MANUAL]),)

    alertifnot = schema.Choice(
        group=_t('Service Status'),
        title=_t('Alert if service is NOT in this state'),
        vocabulary=SimpleVocabulary.fromValues(
            [STATE_RUNNING, STATE_STOPPED]),)


class ServiceDataSourceInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized
    within the WinRS Service plugin.
    """
    implements(IServiceDataSourceInfo)
    adapts(ServiceDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    servicename = ProxyProperty('servicename')
    alertifnot = ProxyProperty('alertifnot')

    def get_startmode(self):
        return self._object.startmode

    def set_startmode(self, value):
        if self._object.startmode != value:
            self._object.startmode = value
            for service in self._object.getAffectedServices():
                service.index_object()

    startmode = property(get_startmode, set_startmode)


class ServicePlugin(PythonDataSourcePlugin):
    proxy_attributes = ConnectionInfoProperties

    @classmethod
    def config_key(cls, datasource, context):
        params = cls.params(datasource, context)
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

        params['alertifnot'] = datasource.talesEval(
            datasource.alertifnot, context)

        params['startmode'] = datasource.talesEval(
            datasource.startmode, context)

        return params

    @defer.inlineCallbacks
    def collect(self, config):

        ds0 = config.datasources[0]

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

    def buildServicesDict(self, datasources):
        services = {}
        for ds in datasources:
            services[ds.params['servicename']] = {'eventClass': ds.eventClass,
                                                  'eventKey': ds.eventKey,
                                                  'severity': ds.severity,
                                                  'alertifnot': ds.params['alertifnot']}
        return services

    def onSuccess(self, results, config):

        data = self.new_data()
        services = self.buildServicesDict(config.datasources)
        log.debug('Windows services query results: {}'.format(results))
        try:
            serviceinfo = results[results.keys()[0]]
        except:
            data['events'].append({
                                'eventClass': "/Status",
                                'severity': ZenEventClasses.Warning,
                                'eventClassKey': 'WindowsServiceCollectionError',
                                'eventKey': 'WindowsServiceCollection',
                                'summary': 'No results returned for service query',
                                'device': config.id})
            return data

        for index in range(0, len(serviceinfo)):
            if serviceinfo[index].State not in services.keys():
                continue

            service = services[serviceinfo[index].Name]
            eventClass = config.datasources[index].eventClass if service['eventClass'] else "/Status"
            eventKey = service['eventKey'] if service['eventKey'] else "WindowsService"

            if serviceinfo[index].State != service['alertifnot']:

                evtmsg = 'Service Alert: {0} has changed to {1} state'.format(
                    serviceinfo[index].Name,
                    serviceinfo[index].State
                )

                data['events'].append({
                    'eventClass': eventClass,
                    'eventClassKey': 'WindowsServiceLog',
                    'eventKey': eventKey,
                    'severity': service['severity'],
                    'summary': evtmsg,
                    'component': prepId(serviceinfo[index].Name),
                    'device': config.id,
                })
            else:

                evtmsg = 'Service Recovered: {0} has changed to {1} state'.format(
                    serviceinfo[index].Name,
                    serviceinfo[index].State
                )

                data['events'].append({
                    'eventClass': eventClass,
                    'eventClassKey': 'WindowsServiceLog',
                    'eventKey': eventKey,
                    'severity': ZenEventClasses.Clear,
                    'summary': evtmsg,
                    'component': prepId(serviceinfo[index].Name),
                    'device': config.id,
                })

        # Event to provide notification that check has completed
        data['events'].append({
            'eventClass': "/Status",
            'device': config.id,
            'summary': 'Windows Service Check: successful service collection',
            'severity': ZenEventClasses.Clear,
            'eventKey': 'WindowsServiceCollection',
            'eventClassKey': 'WindowsServiceLogSuccess',
        })

        return data

    def onError(self, result, config):
        eventClass = "/Status"
        prefix = 'failed collection - '
        if isinstance(result, Failure):
            result = result.value
            if isinstance(result, error.TimeoutError):
                result = 'Timeout while connecting to host'
                prefix = ''
        msg = 'WindowsServiceLog: {0}{1} {2}'.format(prefix, result, config)
        log.error(msg)
        data = self.new_data()
        data['events'].append({
            'eventClass': eventClass,
            'severity': ZenEventClasses.Warning,
            'eventClassKey': 'WindowsServiceCollectionError',
            'eventKey': 'WindowsServiceCollection',
            'summary': msg,
            'device': config.id})
        return data
