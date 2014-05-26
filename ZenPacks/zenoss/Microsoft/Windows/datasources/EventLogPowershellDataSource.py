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
from txwinrm.subscribe import create_event_subscription

from .EventLogDataSource import EventLogDataSource, EventLogInfo
from .EventLogDataSource import ZENPACKID, IEventLogInfo, EventLogPlugin

log = logging.getLogger("zen.MicrosoftWindows")

subscriptions_dct = {}


class EventLogPowershellDataSource(EventLogDataSource):
    sourcetypes = ('Windows EventLog with Powershell',)
    sourcetype = sourcetypes[0]
    plugin_classname = ZENPACKID + \
        '.datasources.EventLogPowershellDataSource.EventLogPowershellPlugin'

class EventLogPowershellInfo(EventLogInfo):
    implements(IEventLogInfo)
    adapts(EventLogPowershellDataSource)

from txwinrm.shell import create_single_shot_command

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

class EventLogPowershellPlugin(EventLogPlugin):
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
            'severity': ZenEventClasses.Info,
            'eventKey': 'WindowsEventCollection',
            'eventClassKey': 'WindowsEventLogSuccess',
        })

        return data
