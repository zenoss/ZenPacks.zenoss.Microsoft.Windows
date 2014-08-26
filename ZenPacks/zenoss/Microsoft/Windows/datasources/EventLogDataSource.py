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
    max_age = 24.0

    plugin_classname = ZENPACKID + \
        '.datasources.EventLogDataSource.EventLogPlugin'

    _properties = PythonDataSource._properties + (
        {'id': 'eventlog', 'type': 'string'},
        {'id': 'query', 'type': 'lines'},
        {'id': 'max_age', 'type': 'float'},
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
    max_age = schema.Text(
        group=_t(u'WindowsEventLog'),
        title=_t('Max age of events to get (hours)'),
    )


class EventLogInfo(RRDDataSourceInfo):
    implements(IEventLogInfo)
    adapts(EventLogDataSource)

    testable = False
    cycletime = ProxyProperty('cycletime')
    eventlog = ProxyProperty('eventlog')
    query = ProxyProperty('query')
    max_age = ProxyProperty('max_age')


def string_to_lines(string):
    if isinstance(string, (list, tuple)):
        return string
    elif hasattr(string, 'splitlines'):
        return string.splitlines()


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
        te = lambda x: datasource.talesEval(x, context)
        return dict(
            eventlog=te(datasource.eventlog), 
            query=te(' '.join(string_to_lines(datasource.query))),
            max_age=te(datasource.max_age), 
            eventid=te(datasource.id)
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
        max_age = ds0.params['max_age']
        eventid = ds0.params['eventid']

        res = yield query.run(eventlog, select, max_age, eventid)
        if res.stderr:
            raise EventLogException('\n'.join(res.stderr))
        output = '\n'.join(res.stdout)
        try:
            value = json.loads(output or '[]') # ConvertTo-Json for empty list returns nothing
            if isinstance(value, dict): # ConvertTo-Json for list of one element returns just that element
                value = [value]
        except ValueError as e:
            log.error('Could not parse json: %r\n%s' % (output, e))
            raise
        defer.returnValue(value)

    def _makeEvent(self, evt, config):
        ds = config.datasources[0].params
        assert isinstance(evt, dict)
        severity = {
            'Error': ZenEventClasses.Error,
            'Warning': ZenEventClasses.Warning,
            'Information': ZenEventClasses.Info,
            'SuccessAudit': ZenEventClasses.Info,
            'FailureAudit': ZenEventClasses.Info,
        }.get(str(evt['EntryType']).strip(), ZenEventClasses.Debug)

        evt = dict(
            device=config.id,
            eventClassKey='%s_%s' % (evt['Source'], evt['InstanceId']),
            eventGroup=ds['eventlog'],
            component=evt['Source'],
            ntevid=evt['InstanceId'],
            summary=evt['Message'],
            severity=severity,
            user=evt['UserName'],
            originaltime=evt['TimeGenerated'],
            computername=evt['MachineName'],
            eventidentifier=evt['EventID'],
        )
        return evt


    def onSuccess(self, results, config):
        data = self.new_data()
        for evt in results:
            data['events'].append(self._makeEvent(evt, config))
        
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
        if isinstance(result.value, EventLogException):
            msg = "WindowsEventLog: failed collection. " + result.value.message
        
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

        function sstring($s) {
            return "$($s)".replace('"', '\"').replace("\'","'").replace('\n','`n').replace('\','\\').trim();
        };
        function EventLogToJSON {
            begin {
                $first = $True;
                '['
            }
            process {
                if ($first) {
                    $separator = "";
                    $first = $False;
                } else {
                    $separator = ",";
                }
                $separator + "{
                    `"EntryType`": `"$(sstring($_.EntryType))`",
                    `"TimeGenerated`": `"$(sstring($_.TimeGenerated))`",
                    `"Source`": `"$(sstring($_.Source))`",
                    `"InstanceId`": `"$(sstring($_.InstanceId))`",
                    `"Message`": `"$(sstring($_.Message))`",
                    `"UserName`": `"$(sstring($_.UserName))`",
                    `"MachineName`": `"$(sstring($_.MachineName))`",
                    `"EventID`": `"$(sstring($_.EventID))`"
                }"
            }
            end {
                ']'
            }
        };

        function get_new_recent_entries($logname, $selector, $max_age, $eventid) {
            <# create HKLM:\SOFTWARE\zenoss\logs if not exists #>
            New-Item HKLM:\SOFTWARE\zenoss -ErrorAction SilentlyContinue;
            New-Item HKLM:\SOFTWARE\zenoss\logs -ErrorAction SilentlyContinue;
            
            <# check the time of last read log entry #>
            $last_read = Get-ItemProperty -Path HKLM:\SOFTWARE\zenoss\logs -Name $eventid -ErrorAction SilentlyContinue;
            
            <# If last log entry was older that 24 hours - read only for last 24 hours #>
            [DateTime]$yesterday = (Get-Date).AddHours(-24);
            [DateTime]$after = $yesterday;
            if ($last_read) {
                $last_read = [DateTime]$last_read.$eventid;
                if ($last_read -gt $yesterday) {
                    $after = $last_read;
                };
            };
            
            <# Fetch events #>
            $events = Get-EventLog -After $after -LogName $logname;
            
            if($events) { <# update the time of last read log entry #>
                [DateTime]$last_read = (@($events)[0]).TimeGenerated; 
                Set-Itemproperty -Path HKLM:\SOFTWARE\zenoss\logs -Name $eventid -Value ([String]$last_read);
            }
            
            @($events | ? $selector) | EventLogToJSON
        };
        get_new_recent_entries -logname %s -selector %s -max_age %s -eventid "%s";
    '''

    def run(self, eventlog, selector, max_age, eventid):
        if selector.strip() == '*':
            selector = '{$True}'
        command = "{0} \"& {{{1}}}\"".format(
            self.PS_COMMAND,
            self.PS_SCRIPT.replace('\n', ' ').replace('"', r'\"') % (
                eventlog or 'System',
                selector or '{$True}',
                max_age or '24',
                eventid
            )
        )
        return self.winrs.run_command(command)

class EventLogException(Exception):
    pass
