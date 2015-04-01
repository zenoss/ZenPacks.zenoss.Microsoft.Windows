##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses WinRS to run remote commands.

See Products.ZenModel.ZenPack._getClassesByPath() to understand how this class
gets discovered as a datasource type in Zenoss.
"""
import json
import logging

from zope.interface import Interface
from zope.component import adapts
from zope.interface import implements

from Products.Zuul.interfaces import IRRDDataSourceInfo
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.Zuul.form import schema
from Products.Zuul.infos.template import RRDDataSourceInfo
from Products.Zuul.infos import ProxyProperty
from Products.ZenUtils import PortScan
from Products.ZenEvents import ZenEventClasses

from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin

ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'
log = logging.getLogger("zen.MicrosoftWindows")

class PortCheckDataSource(PythonDataSource):
    """
    Subclass PythonDataSource to put a new datasources into Zenoss
    """

    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = 300
    ports = ''
    sourcetypes = ('Windows PortCheck',)
    sourcetype = sourcetypes[0]

    _properties = PythonDataSource._properties + (
        {'id': 'ports', 'type': 'string'},
        )

    plugin_classname = ZENPACKID + \
        '.datasources.PortCheckDataSource.PortCheckDataSourcePlugin'

class IPortCheckDataSourceInfo(IRRDDataSourceInfo):
    """
    Provide the UI information for the PortCheck datasource.
    """

    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)'))

    strategy = schema.TextLine(
        group=_t('Port Check'),
        title=_t('Port Check'),
        xtype='portcheck')
    
class PortCheckDataSourceInfo(RRDDataSourceInfo):
    """
    Pull in proxy values so they can be utilized within the PortCheck plugin.
    """
    implements(IPortCheckDataSourceInfo)
    adapts(PortCheckDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    ports = ProxyProperty('ports')

# Subclass due to bug in PortScan.Scanner:  fixed in ZEN-17104
class PortCheckScanner(PortScan.Scanner):
    def recordFailure(self, failure, host, port):
        hostData = self.data['failure'].setdefault(host, [])
        data = (port, failure.getErrorMessage())
        logging.getLogger('zen.Portscanner').debug('Failed to connect to {}:{} -- {}'.format(host, port, data[1]))
        hostData.append(data)

class PortCheckDataSourcePlugin(PythonDataSourcePlugin):

    @classmethod
    def config_key(cls, datasource, context):
        """
        Uniquely pull in datasources
        """
        params = cls.params(datasource, context)
        return(
            context.device().id,
            datasource.getCycleTime(context),
            datasource.id,
            datasource.plugin_classname,
            params.get('ports'),
        )

    @classmethod
    def params(cls, datasource, context):
        return dict(
            ports=datasource.ports)
        
    #@defer.inlineCallbacks
    def collect(self, config):
        dsconf0 = config.datasources[0]

        try:
            self.json_ports = json.loads(dsconf0.params['ports'])
        except:
            log.error('Unable to load ports.  Check configuration')
        
        self.portDict = {}
        for port in self.json_ports:
            self.portDict[int(port['port'])] = port['desc']
        self.scanner = PortCheckScanner(config.manageIp,portList=self.portDict.keys())
        dl = self.scanner.prepare()
        return dl
        
    def onSuccess(self, results, config):
        data = self.new_data()
        dsconf0 = config.datasources[0]
        openPorts = self.scanner.getSuccesses()
        closedPorts = self.scanner.getFailures()
        eventClass = dsconf0.eventClass if dsconf0.eventClass else "/Status"
        eventClassKey = 'WindowsPortCheckStatus'
        try:
            ports = closedPorts[config.manageIp]
            for port in ports:
                # create event
                eventkey = 'WindowsPortCheck{}'.format(port[0])
                msg = 'Port {} is not listening.  {}'.format(port[0], self.portDict[port[0]])
                data['events'].append({
                    'eventClass': eventClass,
                    'severity': dsconf0.severity,
                    'eventClassKey': eventClassKey,
                    'eventKey': eventkey,
                    'summary': msg,
                    'device': config.id})
        except KeyError:
            # nothing to report
            pass
        try:
            ports = openPorts[config.manageIp]
            for port in ports:
                # create event
                eventkey = 'WindowsPortCheck{}'.format(port)
                msg = 'Port {} is listening.  {}'.format(port, self.portDict[port])
                data['events'].append({
                    'eventClass': eventClass,
                    'severity': ZenEventClasses.Clear,
                    'eventClassKey': eventClassKey,
                    'eventKey': eventkey,
                    'summary': msg,
                    'device': config.id})
        except KeyError:
            # no ports listening
            pass
        # send clear events
        return data
    
    def onError(self, results, config):
        data = self.new_data()
        dsconf0 = config.datasources[0]
        
        # send error event
        eventClass = dsconf0.eventClass if dsconf0.eventClass else "/Status"
        eventkey = 'WindowsPortCheckError'
        msg = 'Error running port check tests.  {}'.format(results)
        data['events'].append({
            'eventClass': eventClass,
            'severity': ZenEventClasses.Error,
            'eventClassKey': 'WindowsPortCheckStatus',
            'eventKey': eventkey,
            'summary': msg,
            'device': config.id})
        return data

