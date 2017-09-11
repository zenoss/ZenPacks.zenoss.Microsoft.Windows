##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013-2017, all rights reserved.
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
from Products.ZenEvents import ZenEventClasses

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
import txwinrm.collect  # fix 'module' has no attribute 'collect' error on 4.1.1
import txwinrm.shell  # fix 'module' has no attribute 'shell' error on 4.1.1
from txwinrm.WinRMClient import EnumerateClient, SingleCommandClient, AssociatorClient
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
    associators = {}
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

    def get_associators(self):
        """
        Return Associators list

        To be overridden if commands need to be programmatically defined
        instead of set in the class-level commands property.
        """
        return self.associators

    def client(self, conn_info=None):
        """Return an EnumerateClient if conn_info exists
        """
        if not conn_info:
            return txwinrm.collect.WinrmCollectClient()
        return EnumerateClient(conn_info)

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
        """
        Log an approppriate message for error occurring on device.
        """
        severity = ZenEventClasses.Error
        message, args = (None, [device.id])
        eventClass = '/Status/Winrm'
        if isinstance(error, txwinrm.collect.RequestError):
            message = "Query error on %s: %s"
            html_returned = "<title>404 - File or directory not found.</title>" in error[0]
            if html_returned:
                error = ['HTTP Status: 404. Be sure the WinRM compatibility listener has been configured']
            args.append(error[0])
            if isinstance(error, UnauthorizedError) or html_returned:
                message += ' or check server WinRM settings \n Please refer to winrm documentation at '\
                           'https://www.zenoss.com/product/zenpacks/microsoft-windows'
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
            message = "Credentials cache file not found. Please make sure that this file exists and server has access to it."
            eventClass = '/Status/Kerberos'
        elif type(error) == Exception and 'kerberos' in error.message.lower():
            message = error.message + "  Unable to connect to %s. Please make sure zWinKDC"\
                ", zWinRMUser, zWinRMServerName, and zWinRMPassword "\
                "properties are configured correctly"
            eventClass = '/Status/Kerberos'
        elif isinstance(error, ResponseFailed):
            for reason in error.reasons:
                if isinstance(reason.value, ConnectionLost):
                    message = "Connection lost for %s. Check if WinRM service listening on port %s is working correctly."
                    args.append(device.zWinRMPort)
                elif isinstance(reason.value, SSLError):
                    message = "Connection lost for %s. SSL Error: %s."
                    args.append(', '.join(reason.value.args[0][0]))
        elif isinstance(error, KeyError) and isinstance(error.message, txwinrm.collect.EnumInfo):
            message = "Error on %s: %s.  zWinRMEnvelopeSize may not be large enough.  Increase the size and try again."
            args.append(error)
        else:
            message = "Error on %s: %s"
            args.append(error)

        log.error(message, *args)
        self.error_occurred = message % tuple(args)
        self._send_event(self.error_occurred, device.id, severity, eventClass=eventClass)

    def _send_event(self, reason, id, severity, force=False,
                    key='ConnectionError', eventClass='/Status', summary=None):
        """
        Send event for device with specified id, severity and
        error message.
        """
        log.debug('Sending event: %s' % reason)
        if self._eventService:
            if not summary:
                if severity != ZenEventClasses.Clear:
                    summary = 'Modeler plugin zenoss.winrm.{} returned no results.'.format(self.__class__.__name__)
                else:
                    summary = 'Modeler plugin zenoss.winrm.{} successful.'.format(self.__class__.__name__)
            self._eventService.sendEvent(dict(
                summary=summary,
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
        """
        Collect results of the class' queries and commands.

        This method can be overridden if more complex collection is
        required.
        """
        try:
            conn_info = self.conn_info(device)
        except UnauthorizedError as e:
            msg = "Error on {}: {}".format(device.id, e.message)
            self._send_event(msg, device.id, ZenEventClasses.Error, eventClass='/Status/Winrm', summary=msg)
            raise e
        client = self.client(conn_info)

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
                    query_map.iterkeys())
            except Exception as e:
                self.log_error(log, device, e)
            else:
                for info, data in query_results.iteritems():
                    results[query_map[info]] = data

        # Get associators.
        associators = self.get_associators()

        if associators:
            assoc_client = AssociatorClient(conn_info)
            for assoc_key, associator in associators.iteritems():
                try:
                    if not associator.get('kwargs'):
                        assoc_result = yield assoc_client.associate(
                            associator['seed_class'],
                            associator['associations'])
                    else:
                        assoc_result = yield assoc_client.associate(
                            associator['seed_class'],
                            associator['associations'],
                            **associator['kwargs'])

                except Exception as e:
                    if 'No results for seed class' in e.message:
                        message = 'No results returned for {}. Check WinRM server'\
                                  ' configuration and z properties.'.format(self.name())
                        e = Exception(message)
                    self.log_error(log, device, e)
                else:
                    results[assoc_key] = assoc_result

        # Get a copy of the class' commands.
        commands = dict(self.get_commands())

        # Add PowerShell commands to commands.
        powershell_commands = self.get_powershell_commands()
        if powershell_commands:
            for psc_key, psc in powershell_commands.iteritems():
                commands[psc_key] = '"& {{{}}}"'.format(psc)

        if commands:
            winrs_client = SingleCommandClient(conn_info)
            for command_key, command in commands.iteritems():
                try:
                    if command.startswith('"&'):
                        results[command_key] = yield winrs_client.run_command(POWERSHELL_PREFIX,
                                                                              ps_script=command)
                    else:
                        results[command_key] = yield winrs_client.run_command(command)
                except Exception as e:
                    self.log_error(log, device, e)

        msg = 'Collection completed for %s'
        for eventClass in ('/Status/Winrm', '/Status/Kerberos'):
            self._send_event(msg % device.id, device.id, ZenEventClasses.Clear, eventClass=eventClass)

        defer.returnValue(results)
