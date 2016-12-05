##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014-2016, all rights reserved.
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
import re
from xml.parsers.expat import ExpatError
import xml.dom.minidom
from xml.dom.ext import PrettyPrint
from StringIO import StringIO

from twisted.internet import defer

from zope.component import adapts
from zope.interface import implements
from Products.Zuul.infos import InfoBase
from Products.Zuul.interfaces import IInfo
from Products.Zuul.form import schema
from Products.Zuul.infos import ProxyProperty
from Products.Zuul.utils import ZuulMessageFactory as _t
from Products.ZenEvents import ZenEventClasses

from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSource, PythonDataSourcePlugin

from ..utils import save, errorMsgCheck, generateClearAuthEvents

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo
# Requires that txwinrm_utils is already imported.
from txwinrm.shell import create_single_shot_command


log = logging.getLogger("zen.MicrosoftWindows")
ZENPACKID = 'ZenPacks.zenoss.Microsoft.Windows'

FILTER_XML = '<QueryList><Query Id="0" Path="{logname}"><Select Path="{logname}">*[System[TimeCreated[timediff(@SystemTime) &lt;= {time}]]]</Select></Query></QueryList>'
TIME_CREATED = '[timediff(@SystemTime) &lt;= {time}]'
INSERT_TIME = 'TimeCreated[timediff(@SystemTime) &lt;= {time}] and '


class EventLogDataSource(PythonDataSource):
    ZENPACKID = ZENPACKID
    component = '${here/id}'
    cycletime = '300'
    counter = ''
    sourcetypes = ('Windows EventLog',)
    sourcetype = sourcetypes[0]
    eventlog = ''
    query = '*'
    max_age = '24'
    eventClass = '/Unknown'

    plugin_classname = ZENPACKID + \
        '.datasources.EventLogDataSource.EventLogPlugin'

    _properties = PythonDataSource._properties + (
        {'id': 'eventlog', 'type': 'string'},
        {'id': 'query', 'type': 'string'},
        {'id': 'max_age', 'type': 'string'},
    )


class IEventLogInfo(IInfo):
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
    eventClass = schema.TextLine(
        title=_t(u'Event Class'),
        xtype='eventclass'
    )
    component = schema.TextLine(
       title=_t(u'Component')
    )
    cycletime = schema.TextLine(
        title=_t(u'Cycle Time (seconds)')
    )
    eventlog = schema.TextLine(
        group=_t('WindowsEventLog'),
        title=_t('Event Log')
    )
    query = schema.Text(
        group=_t(u'WindowsEventLog'),
        title=_t('Event Query Powershell or XPath XML'),
        xtype='textarea'
    )
    max_age = schema.TextLine(
        group=_t(u'WindowsEventLog'),
        title=_t('Max age of events to get (hours)'),
    )


class EventLogInfo(InfoBase):
    implements(IEventLogInfo)
    adapts(EventLogDataSource)

    def __init__(self, dataSource):
        self._object = dataSource

    @property
    def id(self):
        return '/'.join(self._object.getPrimaryPath())

    @property
    def source(self):
        return self._object.getDescription()

    @property
    def type(self):
        return self._object.sourcetype

    @property
    def newId(self):
        return self._object.id

    # severity = property(_getSeverity, _setSeverity)
    enabled = ProxyProperty('enabled')
    component = ProxyProperty('component')
    eventClass = ProxyProperty('eventClass')
    testable = False
    cycletime = ProxyProperty('cycletime')
    eventlog = ProxyProperty('eventlog')
    max_age = ProxyProperty('max_age')

    def set_query(self, value):
        if self._object.query != value:
            try:
                in_filter_xml = xml.dom.minidom.parseString(value)
            except ExpatError:
                self._object.query = value
                return
            for node in in_filter_xml.getElementsByTagName('Select'):
                filter_text = node.childNodes[0].data
                time_match = re.match('(.*TimeCreated)(\[.*?\])(.*)', filter_text)
                if time_match:
                    # easy to replace with our time filter
                    filter_text = time_match.group(1)+TIME_CREATED+time_match.group(3)
                else:
                    # need to insert our time filter
                    notime_match = re.match('(\*\[System\[)(.*)', filter_text)
                    filter_text = notime_match.group(1)+INSERT_TIME+notime_match.group(2)
                node.childNodes[0].data = filter_text
            xml_query = prettify_xml(in_filter_xml)
            # undo replacement of single quotes with double            
            xml_query = re.sub(r"(\w+)='(\w+)'", r'\1="\2"', xml_query)
            # remove the xml header and replace any "&amp;" with "&"
            header = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n'
            xml_query = xml_query.replace(header, '').replace('&amp;', '&')
            self._object.query = xml_query

    def get_query(self):
        return self._object.query

    query = property(get_query, set_query)


def string_to_lines(string):
    if isinstance(string, (list, tuple)):
        return string
    if isinstance(string, (unicode, str)):
        return str(string).splitlines()
    log.warn('Could not convert string to lines: %s' % str(string))
    return []

def prettify_xml(xml):
    '''preserve XML formatting'''
    iostream = StringIO()
    PrettyPrint(xml, stream=iostream)
    output = iostream.getvalue()
    iostream.close()
    return output


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
        query = datasource.query
        query_error = True

        try:
            query = te(' '.join(string_to_lines(datasource.query)))
            query_error = False
        except Exception:
            pass
        try:
            xml.dom.minidom.parseString(query)
            use_xml = True
        except ExpatError:
            use_xml = False

        return dict(
                eventlog=te(datasource.eventlog),
                query=query,
                query_error=query_error,
                max_age=te(datasource.max_age),
                eventid=te(datasource.id),
                use_xml=use_xml,
                eventClass=datasource.eventClass
            )

    @defer.inlineCallbacks
    def collect(self, config):
        log.info('Start Collection of Events')

        ds0 = config.datasources[0]

        if ds0.params['query_error']:
            e = EventLogException('Please verify EventQuery on datasource %s'
                                  % ds0.params['eventid'])
            value = [e]
            raise e

        conn_info = createConnectionInfo(ds0)

        query = EventLogQuery(conn_info)

        eventlog = ds0.params['eventlog']
        select = ds0.params['query']
        max_age = ds0.params['max_age']
        eventid = ds0.params['eventid']
        isxml = ds0.params['use_xml']

        res = None
        output = []

        try:
            res = yield query.run(eventlog, select, max_age, eventid, isxml)
        except Exception as e:
            if 'Password expired' in e.message:
                raise e
            log.error(e)
        try:
            if res.stderr:
                str_err = '\n'.join(res.stderr)
                log.debug('Event query error: {}'.format(str_err))
                if str_err.find('No events were found that match the specified selection criteria') != -1:
                    # no events found.  expected error.
                    pass
                elif (str_err.startswith('Get-WinEvent : The specified channel could not be found.')) \
                        or "does not exist" in str_err:
                    err_msg = "Event Log '%s' does not exist in %s" % (eventlog, ds0.device)
                    raise MissedEventLogException(err_msg)
                elif str_err.startswith('Where-Object : Cannot bind parameter \'FilterScript\'. Cannot convert the'):
                    err_msg = "EventQuery value provided in datasource '{}' is not valid".format(ds0.params['eventid'])
                    raise InvalidEventQueryValue(err_msg)
                else:
                    raise EventLogException(str_err)
            output = '\n'.join(res.stdout)
        except AttributeError:
            pass
        try:
            log.debug(output)
            value = json.loads(output or '[]')  # ConvertTo-Json for empty list returns nothing
            if isinstance(value, dict):  # ConvertTo-Json for list of one element returns just that element
                value = [value]
        except UnicodeDecodeError:
            # replace unknown characters with '?'
            value = json.loads(unicode(output.decode("utf-8", "replace")))
            if isinstance(value, dict):  # ConvertTo-Json for list of one element returns just that element
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
        # Fixes ZEN-23024
        # only assign event class if other than '/Unknown', otherwise
        # the user should use event class mappings
        eventClass = ds.get('eventClass')
        if eventClass and eventClass != '/Unknown':
            evt['eventClass'] = eventClass
        return evt

    @save
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

        generateClearAuthEvents(config, data['events'])

        return data

    @save
    def onError(self, result, config):
        msg = 'WindowsEventLog: failed collection {0} {1}'.format(result.value.message, config)
        if isinstance(result.value, EventLogException):
            msg = "WindowsEventLog: failed collection. " + result.value.message
        if isinstance(result.value, (MissedEventLogException, InvalidEventQueryValue)):
            msg = "WindowsEventLog: " + result.value.message
        severity = ZenEventClasses.Warning
        if 'This cmdlet requires Microsoft .NET Framework version 3.5 or greater' in msg:
            severity = ZenEventClasses.Critical
        log.error(msg)
        data = self.new_data()
        errorMsgCheck(config, data['events'], result.value.message)
        if not data['events']:
            data['events'].append({
                'severity': severity,
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

    PS_SCRIPT = '''
        $FormatEnumerationLimit = -1;
        $Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size(4096, 25);
        function sstring($s) {{
            if ($s -eq $null) {{
                return "";
            }};
            if ($s.GetType() -eq [System.Security.Principal.SecurityIdentifier]) {{
                [String]$s = $s.Translate( [System.Security.Principal.NTAccount]);
            }} elseif ($s.GetType() -ne [String]) {{
                [String]$s = $s;
            }};
            $s = $s.replace("`r","").replace("`n"," ");
            $s = $s.replace('"', '\\"').replace("\\'","'");
            $s = $s.replace("`t", " ");
            return "$($s)".replace('\\','\\\\').trim();
        }};
        function EventLogToJSON {{
            begin {{
                $first = $True;
                '['
            }}
            process {{
                if ($first) {{
                    $separator = "";
                    $first = $False;
                }} else {{
                    $separator = ",";
                }}
                $separator + "{{
                    `"EntryType`": `"$(sstring($_.EntryType))`",
                    `"TimeGenerated`": `"$(sstring($_.TimeGenerated))`",
                    `"Source`": `"$(sstring($_.Source))`",
                    `"InstanceId`": `"$(sstring($_.InstanceId))`",
                    `"Message`": `"$(sstring($_.Message))`",
                    `"UserName`": `"$(sstring($_.UserName))`",
                    `"MachineName`": `"$(sstring($_.MachineName))`",
                    `"EventID`": `"$(sstring($_.EventID))`"
                }}"
            }}
            end {{
                ']'
            }}
        }};
        function EventLogRecordToJSON {{
            begin {{
                $first = $True;
                '['
            }}
            process {{
                if ($first) {{
                    $separator = "";
                    $first = $False;
                }} else {{
                    $separator = ",";
                }}
                $separator + "{{
                    `"EntryType`": `"$(sstring($_.LevelDisplayName))`",
                    `"TimeGenerated`": `"$(sstring($_.TimeCreated))`",
                    `"Source`": `"$(sstring($_.ProviderName))`",
                    `"InstanceId`": `"$(sstring($_.Id))`",
                    `"Message`": `"$(if ($_.Message){{$(sstring($_.Message))}}else{{$(sstring($_.FormatDescription()))}})`",
                    `"UserName`": `"$(sstring($_.UserId))`",
                    `"MachineName`": `"$(sstring($_.MachineName))`",
                    `"EventID`": `"$(sstring($_.Id))`"
                }}"
            }}
            end {{
                ']'
            }}
        }};
        function get_new_recent_entries($logname, $selector, $max_age, $eventid) {{
            $x=New-Item HKCU:\SOFTWARE\zenoss -ea SilentlyContinue;
            $x=New-Item HKCU:\SOFTWARE\zenoss\logs -ea SilentlyContinue;
            $last_read = Get-ItemProperty -Path HKCU:\SOFTWARE\zenoss\logs -Name  $eventid -ea SilentlyContinue;
            [DateTime]$yesterday = (Get-Date).AddHours(-$max_age);
            [DateTime]$after = $yesterday;
            if ($last_read) {{
                $last_read = [DateTime]$last_read.$eventid;
                if ($last_read -gt $yesterday) {{
                    $after = $last_read;
                }};
            }};
            $win2003 = [environment]::OSVersion.Version.Major -lt 6;
            $dotnets = Get-ChildItem 'HKLM:\\software\\microsoft\\net framework setup\\ndp'| % {{$_.name.split('\\')[5]}} | ? {{ $_ -match 'v3.5|v[45].*'}};
            if ($win2003 -eq $false -and $dotnets -ne $null) {{
                $query = '{filter_xml}';
                [Array]$events = Get-WinEvent -FilterXml $query.replace("{{logname}}",$logname).replace("{{time}}", ((Get-Date) - $after).TotalMilliseconds);
            }} else {{
                [Array]$events = Get-EventLog -After $after -LogName $logname;
            }};
            [DateTime]$last_read = get-date;
            Set-Itemproperty -Path HKCU:\SOFTWARE\zenoss\logs -Name $eventid -Value ([String]$last_read);
            if ($events -eq $null) {{
                return;
            }};
            if($events) {{
                [Array]::Reverse($events);
            }};
            if ($win2003 -and $dotnets -eq $null) {{
                @($events | ? $selector) | EventLogToJSON
            }}
            else {{
                @($events | ? $selector) | EventLogRecordToJSON
            }}
        }};
        function Use-en-US ([ScriptBlock]$script= (throw))
        {{
            $CurrentCulture = [System.Threading.Thread]::CurrentThread.CurrentCulture;
            [System.Threading.Thread]::CurrentThread.CurrentCulture = New-Object "System.Globalization.CultureInfo" "en-Us";
            Invoke-Command $script;
            [System.Threading.Thread]::CurrentThread.CurrentCulture = $CurrentCulture;
        }};
        Use-en-US {{get_new_recent_entries -logname "{eventlog}" -selector {selector} -max_age {max_age} -eventid "{eventid}"}};
    '''

    def run(self, eventlog, selector, max_age, eventid, isxml):
        if selector.strip() == '*':
            selector = '{$True}'
        if isxml:
            filter_xml = selector.replace('\n', ' ').replace('"', r'\"')
            selector = '{$True}'
        else:
            filter_xml = FILTER_XML.replace('"', r'\"')
        ps_script = ' '.join([x.strip() for x in self.PS_SCRIPT.split('\n')])
        command = "{0} \"& {{{1}}}\"".format(
            self.PS_COMMAND,
            ps_script.replace('\n', ' ').replace('"', r'\"').format(
                eventlog=eventlog or 'System',
                selector=selector or '{$True}',
                max_age=max_age or '24',
                eventid=eventid,
                filter_xml=filter_xml
            )
        )
        log.debug('sending event script: {}'.format(command))
        return self.winrs.run_command(command)


class EventLogException(Exception):
    pass


class MissedEventLogException(Exception):
    pass


class InvalidEventQueryValue(Exception):
    pass
