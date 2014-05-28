##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses Powershell comandlet to collect Windows Event Logs

"""

import logging
import json

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

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo

# Requires that txwinrm_utils is already imported.
from txwinrm.shell import create_single_shot_command


log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'

class EventLogDataSource(PythonDataSource):
    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = 300
    counter = ''
    strategy = ''
    sourcetypes = ('Windows EventLog',)
    sourcetype = sourcetypes[0]
    eventlog = ''
    query = ''

    plugin_classname = ZENPACKID + \
        '.datasources.EventLogDataSource.EventLogPlugin'

    _properties = PythonDataSource._properties + (
        {'id': 'eventlog', 'type': 'string'},
        {'id': 'query', 'type': 'lines'},
    )


class IEventLogInfo(IRRDDataSourceInfo):
    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)')
    )
    eventlog = schema.TextLine(
        group=_t('WindowsEventLog'),
        title=_t('Event Log')
    )
    query = schema.Text(
        group=_t(u'WindowsEventLog'),
        title=_t('Event Query'),
        xtype='twocolumntextarea'
    )


class EventLogInfo(RRDDataSourceInfo):
    implements(IEventLogInfo)
    adapts(EventLogDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    eventlog = ProxyProperty('eventlog')
    query = ProxyProperty('query')


def string_to_lines(string):
    if isinstance(string, (list, tuple)):
        return string
    elif hasattr(string, 'splitlines'):
        return string.splitlines()

    return None


class EventLogPlugin(PythonDataSourcePlugin):
    proxy_attributes = ConnectionInfoProperties

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
        return dict(
            eventlog=datasource.talesEval(
                datasource.eventlog, context
            ), 
            query=datasource.talesEval(
                ' '.join(string_to_lines(datasource.query)),
                context
            )
        )

    @defer.inlineCallbacks
    def collect(self, config):
        results = []
        log.info('Start Collection of Events')

        ds0 = config.datasources[0]
        conn_info = createConnectionInfo(ds0)

        query = EventLogQuery(conn_info)

        eventlog = ds0.params['eventlog']
        select = ds0.params['query']

        res = yield query.run(eventlog, select)
        defer.returnValue(json.loads(
            '\n'.join(res.stdout)
        ))


    def onSuccess(self, results, config):
        data = self.new_data()
        for evt in results:
            severity = {
                'Information': ZenEventClasses.Clear,
                'Warning': ZenEventClasses.Warning,
                'Error': ZenEventClasses.Critical,
            }.get(evt['severity'], ZenEventClasses.Info)

            data['events'].append({
                'eventClassKey': 'WindowsEventLog',
                'eventKey': 'WindowsEvent',
                'severity': severity,
                'summary': 'Collected Event: %s' % evt['message'],
                'device': config.id,
            })

        data['events'].append({
            'device': config.id,
            'summary': 'Windows EventLog: successful event collection',
            'severity': ZenEventClasses.Clear,
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
            'device': config.id
        })
        return data


class EventLogQuery(object):
    def __init__(self, conn_info):
        self.winrs = create_single_shot_command(conn_info)

    PS_COMMAND = "powershell -NoLogo -NonInteractive -NoProfile " \
            "-OutputFormat TEXT -Command "

    PS_SCRIPT = r'''
        $FormatEnumerationLimit = -1;
        $Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(4096, 25);

        function get_new_recent_entries($logname, $selector={$True}) { 
            <# create HKLM:\SOFTWARE\zenoss\logs if not exists #>
            New-Item HKLM:\SOFTWARE\zenoss -ErrorAction SilentlyContinue;
            New-Item HKLM:\SOFTWARE\zenoss\logs -ErrorAction SilentlyContinue;
            
            <# check the time of last read log entry #>
            $last_read = Get-ItemProperty -Path HKLM:\SOFTWARE\zenoss\logs -Name $logname -ErrorAction SilentlyContinue;
            
            <# If last log entry was older that 24 hours - read only for last 24 hours #>
            [DateTime]$yesterday = (Get-Date).AddHours(-24);
            [DateTime]$after = $yesterday;
            if ($last_read) {
                $last_read = [DateTime]$last_read.$logname;
                if ($last_read -gt $yesterday) {
                    $after = $last_read;
                };
            };
            
            <# Fetch events #>
            $events = Get-EventLog -After $after -LogName $logname;
            
            if($events) { <# update the time of last read log entry #>
                [DateTime]$last_read = (@($events)[0]).TimeGenerated; 
                Set-Itemproperty -Path HKLM:\SOFTWARE\zenoss\logs -Name $logname -Value ([String]$last_read);
            }
            
            '[' + (($events | ? $selector | %% { "{
                `"severity`": `"$($_.EntryType)`",
                `"message`": `"Collected Event: EventID: $($_.EventID)\nSource: $($_.Source)\nMessage: $($_.Message)`"
            }" }) -join ', ') + ']'
        };
        get_new_recent_entries %s %s;
    '''

    def run(self, eventlog, selector):
        command = "{0} \"& {{{1}}}\"".format(
            self.PS_COMMAND,
            self.PS_SCRIPT.replace('\n', ' ').replace('"', r'\"') % (eventlog, selector)
        )
        return self.winrs.run_command(command)


