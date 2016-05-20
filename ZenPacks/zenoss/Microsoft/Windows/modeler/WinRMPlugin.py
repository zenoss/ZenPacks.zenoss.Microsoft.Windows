##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
import types
import socket

from xml.etree.cElementTree import ParseError as cParseError

from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin

from twisted.internet import defer
from twisted.internet.error import (
    ConnectError,
    ConnectionRefusedError,
    TimeoutError,
    ConnectionLost,
    )
from twisted.web._newclient import ResponseFailed
from OpenSSL.SSL import Error as SSLError

from ..txwinrm_utils import ConnectionInfoProperties, createConnectionInfo

# Requires that txwinrm_utils is already imported.
import txwinrm
import txwinrm.collect # fix 'module' has no attribute 'collect' error on 4.1.1 
import txwinrm.shell # fix 'module' has no attribute 'shell' error on 4.1.1
import zope.component

from txwinrm.util import UnauthorizedError
from Products.ZenCollector.interfaces import IEventService

log = logging.getLogger("zen.MicrosoftWindows")

# Format string for a resource URI.
RESOURCE_URI_FORMAT = 'http://schemas.microsoft.com/wbem/wsman/1/wmi/root/{}/*'

# PowerShell command prefix.
POWERSHELL_PREFIX = 'powershell -NoLogo -NonInteractive -NoProfile -OutputFormat TEXT -Command'


class WinRMPlugin(PythonPlugin):
    '''
    Base modeler plugin class for WinRM modeler plugins.
    '''

    deviceProperties = PythonPlugin.deviceProperties + ConnectionInfoProperties

    queries = {}
    commands = {}
    powershell_commands = {}
    _eventService = zope.component.queryUtility(IEventService)

    def get_queries(self):
        '''
        Return queries dictionary.

        To be overridden if queries need to be programmatically defined
        instead of set in the class-level queries property.
        '''
        return self.queries

    def get_commands(self):
        '''
        Return commands list.

        To be overridden if commands need to be programmatically defined
        instead of set in the class-level commands property.
        '''
        return self.commands

    def get_powershell_commands(self):
        '''
        Return PowerShell commands list.

        To be overridden if powershell_commands needs to be
        programmatically defined instead of set in the class-level
        commands property.
        '''
        return self.powershell_commands

    def client(self):
        '''
        Return a WinrmCollectClient.
        '''
        return txwinrm.collect.WinrmCollectClient()

    def conn_info(self, device):
        '''
        Return a ConnectionInfo given device.
        '''
        return createConnectionInfo(device)

    def enuminfo(self, query, resource_uri=None, namespace=None):
        '''
        Return EnumInfo object given query and either resource_uri or
        namespace.

        If neither resource_uri or namespace are given the default
        namespace will be used. resource_uri will be used in preference
        to namespace if they're both provided.
        '''
        if not resource_uri:
            resource_uri = RESOURCE_URI_FORMAT.format(namespace or 'cimv2')

        return txwinrm.collect.create_enum_info(
            query, resource_uri=resource_uri)

    def enuminfo_tuples(self):
        '''
        Generate (key, EnumInfo) tuples for each of class' queries.
        '''
        for key, data in self.get_queries().iteritems():
            query = None
            resource_uri = None
            namespace = None

            if isinstance(data, types.StringTypes):
                query = data
            elif isinstance(data, dict):
                query = data.get('query')
                resource_uri = data.get('resource_uri')
                namespace = data.get('namespace')

            enuminfo = self.enuminfo(
                query,
                resource_uri=resource_uri,
                namespace=namespace)

            yield (key, enuminfo)

    def log_error(self, log, device, error):
        '''
        Log an approppriate message for error occurring on device.
        '''
        message, args = (None, [device.id])
        if isinstance(error, txwinrm.collect.RequestError):
            message = "Query error on %s: %s"
            args.append(error[0])
            if isinstance(error, UnauthorizedError):
                message += ' or check server WinRM settings \n Please refer to txwinrm documentation at '\
                            'http://wiki.zenoss.org/ZenPack:Microsoft_Windows#winrm_setup'
        elif isinstance(error, ConnectionRefusedError):
            message = "Connection refused on %s: Verify WinRM setup"
        elif isinstance(error, TimeoutError):
            message = "Timeout on %s: Verify WinRM and firewall setup"
        elif isinstance(error, ConnectError):
            message = "Connection error on %s: %s"
            args.append(error.message)
        elif isinstance(error, cParseError) and 'line 1, column 0' in error.msg:
            message = "Error on %s: Check WinRM AllowUnencrypted is set to true"
        elif type(error) == Exception and "Credentials cache file" in error.message:
            message = "Credentials cache file not found. Please make sure that this file exist and server has  access to it."
        elif type(error) == Exception and error.message.startswith('kerberos authGSSClientStep failed'):
            message = "Unable to connect to %s. Please make sure zWinKDC, zWinRMUser and zWinRMPassword property is configured correctly"
        elif isinstance(error, ResponseFailed):
            for reason in error.reasons:
                if isinstance(reason.value, ConnectionLost):
                    message = "Connection lost for %s. Check if WinRM service listening on port %s is working correctly."
                    args.append(device.zWinRMPort)
                elif isinstance(reason.value, SSLError):
                    message = "Connection lost for %s. SSL Error: %s."
                    args.append(', '.join(reason.value.args[0][0]))
                log.error(message, *args)
            return

        else:
            message = "Error on %s: %s"
            args.append(error)

        log.error(message, *args)
        self._send_event(message % tuple(args), device.id, 3, eventClass='/Status/Winrm')

    def _send_event(self, reason, id, severity, force=False,
                    key='ConnectionError', eventClass='/Status'):
        """
        Send event for device with specified id, severity and
        error message.
        """
        log.debug('Sending event: %s' % reason)
        if self._eventService:
            self._eventService.sendEvent(dict(
                summary='Modeler plugin zenoss.winrm.%s returned no results.' % self.__class__.__name__,
                message=reason,
                eventClass=eventClass,
                eventClassKey=key,
                device=id,
                eventKey=self.__class__.__name__,
                severity=severity,
            ))
            return True

    def get_ip_and_hostname(self, ip_or_hostname):
        """
        Return a list which contains hostname and IP

        socket.gethostbyaddr('127.0.0.1')
        ('localhost.localdomain', ['localhost'], ['127.0.0.1'])
        socket.gethostbyaddr('localhost.localdomain')
        ('localhost.localdomain', ['localhost'], ['127.0.0.1'])
        """
        try:
            hostbyaddr = socket.gethostbyaddr(ip_or_hostname)
            hostbyaddr[2].append(hostbyaddr[0])
            return hostbyaddr[2]
        except socket.error:
            return []

    @defer.inlineCallbacks
    def collect(self, device, log):
        '''
        Collect results of the class' queries and commands.

        This method can be overridden if more complex collection is
        required.
        '''
        client = self.client()
        conn_info = self.conn_info(device)

        results = {}
        queries = self.get_queries()
        if queries:
            query_map = {
                enuminfo: key for key, enuminfo in self.enuminfo_tuples()}

            # Silence winrm logging. We want to control the message.
            winrm_log = logging.getLogger('winrm')
            winrm_log.setLevel(logging.FATAL)

            try:
                query_results = yield client.do_collect(
                    conn_info, query_map.iterkeys())
                msg = "connection for %s is established"
                self._send_event(msg % device.id, device.id, 0, eventClass='/Status/Winrm/Ping')
            except Exception as e:
                self.log_error(log, device, e)
            else:
                for info, data in query_results.iteritems():
                    results[query_map[info]] = data

            # Unset winrm logging. Will fallback to root logger level.
            # winrm_log.setLevel(logging.NOTSET)

        # Get a copy of the class' commands.
        commands = dict(self.get_commands())

        # Add PowerShell commands to commands.
        powershell_commands = self.get_powershell_commands()
        if powershell_commands:
            for psc_key, psc in powershell_commands.iteritems():
                commands[psc_key] = '{0} "& {{{1}}}"'.format(
                    POWERSHELL_PREFIX, psc)

        if commands:
            winrs = txwinrm.shell.create_single_shot_command(conn_info)

            for command_key, command in commands.iteritems():
                try:
                    results[command_key] = yield winrs.run_command(command)
                    msg = 'shell command completed successfully for %s'
                    self._send_event(msg % device.id, device.id, 0, eventClass='/Status/Winrm/Ping')
                except Exception as e:
                    self.log_error(log, device, e)

        defer.returnValue(results)
