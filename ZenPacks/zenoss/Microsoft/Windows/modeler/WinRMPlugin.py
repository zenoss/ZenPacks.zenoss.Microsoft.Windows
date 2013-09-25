##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin

from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath
addLocalLibPath()

import txwinrm


class WinRMPlugin(PythonPlugin):
    '''
    Base modeler plugin class for WinRM modeler plugins.
    '''

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        'zWinRMPort',
        )

    wql_queries = []

    def client(self):
        '''
        Return a WinrmCollectClient.
        '''
        return txwinrm.collect.WinrmCollectClient()

    def conn_info(self, device):
        '''
        Return a ConnectionInfo given device.
        '''
        hostname = device.manageIp
        username = device.zWinUser
        auth_type = 'kerberos' if '@' in username else 'basic'
        password = device.zWinPassword
        scheme = 'http'
        port = int(device.zWinRMPort)
        connectiontype = 'Keep-Alive'
        keytab = ''

        return txwinrm.collect.ConnectionInfo(
            hostname,
            auth_type,
            username,
            password,
            scheme,
            port,
            connectiontype,
            keytab)

    def create_enum_info(self, wql, resource_uri=None):
        if not resource_uri:
            resource_uri = txwinrm.enumerate.DEFAULT_RESOURCE_URI

        return txwinrm.collect.create_enum_info(wql, resource_uri=resource_uri)

    def collect(self, device, log):
        '''
        Collect results of the class' queries list.

        This method should be overridden if more complex collection is
        required.
        '''
        client = self.client()
        conn_info = self.conn_info(device)

        if not self.wql_queries:
            log.error("Modeler %s has no WQL queries defined")
            return

        return client.do_collect(
            conn_info, map(self.create_enum_info, self.wql_queries))
