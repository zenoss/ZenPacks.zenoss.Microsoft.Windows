##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
from twisted.internet import defer
from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource \
    import PythonDataSourcePlugin
from .txwinrm.util import ConnectionInfo
from .txwinrm.shell import create_single_shot_command

log = logging.getLogger("zen.MicrosoftWindows")


class SingleShotPlugin(PythonDataSourcePlugin):

    proxy_attributes = ('zWinUser', 'zWinPassword')

    @defer.inlineCallbacks
    def collect(self, config):
        log.debug('TypeperfSc1Plugin collect {0}'.format(config))
        scheme = 'http'
        port = 5985
        results = []
        for datasource in config.datasources:
            auth_type = 'basic'
            if '@' in datasource.zWinUser:
                auth_type = 'kerberos'
            conn_info = ConnectionInfo(
                datasource.manageIp,
                auth_type,
                datasource.zWinUser,
                datasource.zWinPassword,
                scheme,
                port)
            cmd = create_single_shot_command(conn_info)
            command_line = self._build_command_line(datasource.counter)
            result = yield cmd.run_command(command_line)
            results.append((datasource, result))
        defer.returnValue(results)

    def onSuccess(self, results, config):
        log.debug('TypeperfPlugin onSuccess {0} {1}'.format(results, config))
        data = self.new_data()
        self._parse_results(results, data)
        data['events'].append(dict(
            eventClassKey='typeperfCollectionSuccess',
            eventKey='typeperfCollection',
            summary='typeperf: successful collection',
            device=config.id))
        return data

    def onError(self, result, config):
        msg = 'typeperf: failed collection {0} {1}'.format(result, config)
        log.error(msg)
        data = self.new_data()
        data['events'].append(dict(
            eventClassKey='typeperfCollectionError',
            eventKey='typeperfCollection',
            summary=msg,
            device=config.id))
        return data


class TypeperfSc1Plugin(SingleShotPlugin):

    def _build_command_line(self, counter):
        'typeperf "{0}" -sc 1'.format(counter)

    def _parse_results(self, results, data):
        for ds, result in results:
            timestamp, value = result.split(',')
            data['values'][ds.component][ds.datasource] = (value, timestamp)
            pass


class PowershellGetCounterPlugin(SingleShotPlugin):

    def _build_command_line(self, counter):
        return "powershell -NoLogo -NonInteractive -NoProfile -OutputFormat " \
               "XML -Command \"get-counter -counter '{0}'\"".format(counter)

    def _parse_results(self, results, data):
        for datasource, result in results:
            # data['values']
            pass
