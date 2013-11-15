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

from twisted.internet import defer

import txwinrm


class WinRMPlugin(PythonPlugin):
    '''
    Base modeler plugin class for WinRM modeler plugins.
    '''

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        'zWinRMPort',
        'zWinKDC',
        'zWinKeyTabFilePath',
        'zWinScheme',
        )

    wql_queries = {}

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
        scheme = device.zWinScheme
        port = int(device.zWinRMPort)
        connectiontype = 'Keep-Alive'
        keytab = device.zWinKeyTabFilePath
        dcip = device.zWinKDC

        return txwinrm.collect.ConnectionInfo(
            hostname,
            auth_type,
            username,
            password,
            scheme,
            port,
            connectiontype,
            keytab,
            dcip)

    def create_enum_info(self, wql, resource_uri=None):
        if not resource_uri:
            resource_uri = txwinrm.enumerate.DEFAULT_RESOURCE_URI

        return txwinrm.collect.create_enum_info(wql, resource_uri=resource_uri)

    @defer.inlineCallbacks
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

        for query_key in self.wql_queries:
            log.info("Querying %s on %s", query_key, device.id)

        try:
            collect_results = yield client.do_collect(
                conn_info, map(
                    self.create_enum_info,
                    self.wql_queries.values()))

        except txwinrm.collect.RequestError as e:
            log.error(e[0])
            raise

        inverted_wql_queries = {v: k for k, v in self.wql_queries.iteritems()}

        results = {}
        for info, data in collect_results.iteritems():
            results[inverted_wql_queries[info.wql]] = data

        defer.returnValue(results)
