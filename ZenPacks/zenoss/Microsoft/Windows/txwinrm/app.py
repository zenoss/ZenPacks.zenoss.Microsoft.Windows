##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import sys
import logging
from getpass import getpass
from urlparse import urlparse
from argparse import ArgumentParser
from ConfigParser import RawConfigParser
from twisted.internet import reactor, defer
from twisted.internet.error import TimeoutError
from .enumerate import create_winrm_client
from .util import ConnectionInfo, verify_conn_info, UnauthorizedError

logging.basicConfig()
log = logging.getLogger('zen.winrm')
_exit_status = 0
DEFAULT_SCHEME = 'http'
DEFAULT_PORT = 5985


def get_vmpeak():
    with open('/proc/self/status') as status:
        for line in status:
            key, value = line.split(None, 1)
            if key == 'VmPeak:':
                return value


@defer.inlineCallbacks
def get_remote_process_stats(client):
    wql = 'select Name, IDProcess, PercentProcessorTime,' \
          'Timestamp_Sys100NS from Win32_PerfRawData_PerfProc_Process ' \
          'where name like "wmi%"'
    items = yield client.enumerate(wql)
    defer.returnValue(items)


def calculate_remote_cpu_util(initial_stats, final_stats):
    cpu_util_info = []
    for hostname, initial_stats_items in initial_stats.iteritems():
        final_stats_items = final_stats[hostname]
        host_cpu_util_info = []
        cpu_util_info.append([hostname, host_cpu_util_info])
        for initial_stats_item in initial_stats_items:
            name = initial_stats_item.Name
            pid = initial_stats_item.IDProcess
            for final_stats_item in final_stats_items:
                if pid == final_stats_item.IDProcess:
                    break
            else:
                print >>sys.stderr, "WARNING: Could not find final process " \
                                    "stats for", hostname, pid
                continue
            x1 = float(final_stats_item.PercentProcessorTime)
            x0 = float(initial_stats_item.PercentProcessorTime)
            y1 = float(final_stats_item.Timestamp_Sys100NS)
            y0 = float(initial_stats_item.Timestamp_Sys100NS)
            cpu_pct = (x1 - x0) / (y1 - y0)
            host_cpu_util_info.append((cpu_pct, name, pid))
    return cpu_util_info


def print_remote_cpu_util(cpu_util_info):
    for hostname, stats in cpu_util_info:
        print >>sys.stderr, "   ", hostname
        for cpu_pct, name, pid in stats:
            fmt = "      {cpu_pct:.2%} of CPU time used by {name} "\
                  "process with pid {pid}"
            print >>sys.stderr, fmt.format(hostname=hostname, cpu_pct=cpu_pct,
                                           name=name, pid=pid)


@defer.inlineCallbacks
def get_initial_wmiprvse_stats(config):
    initial_wmiprvse_stats = {}
    good_conn_infos = []
    for conn_info in config.conn_infos:
        try:
            client = create_winrm_client(conn_info)
            initial_wmiprvse_stats[conn_info.hostname] = \
                yield get_remote_process_stats(client)
            good_conn_infos.append(conn_info)
        except UnauthorizedError:
            continue
        except TimeoutError:
            continue
    defer.returnValue((initial_wmiprvse_stats, good_conn_infos))


class ConfigDrivenUtility(object):

    def __init__(self, strategy):
        self._strategy = strategy

    @defer.inlineCallbacks
    def tx_main(self, args, config):
        global _exit_status
        do_summary = len(config.conn_infos) > 1
        if do_summary:
            initial_wmiprvse_stats, good_conn_infos = \
                yield get_initial_wmiprvse_stats(config)
        else:
            initial_wmiprvse_stats = None
            good_conn_infos = [config.conn_infos[0]]
        if not good_conn_infos:
            _exit_status = 1
            stop_reactor()
            return

        @defer.inlineCallbacks
        def callback(results):
            if do_summary:
                yield self._print_summary(
                    results, config, initial_wmiprvse_stats, good_conn_infos)

        d = self._strategy.act(good_conn_infos, args, config)
        d.addCallback(callback)
        d.addBoth(stop_reactor)

    @defer.inlineCallbacks
    def _print_summary(
            self, results, config, initial_wmiprvse_stats, good_conn_infos):
        global _exit_status
        final_wmiprvse_stats = {}
        for conn_info in good_conn_infos:
            client = create_winrm_client(conn_info)
            final_wmiprvse_stats[conn_info.hostname] = \
                yield get_remote_process_stats(client)
        print >>sys.stderr, '\nSummary:'
        print >>sys.stderr, '  Connected to', len(good_conn_infos), 'of', \
                            len(config.conn_infos), 'hosts'
        print >>sys.stderr, "  Processed", self._strategy.count_summary
        if results is not None:
            failure_count = 0
            for success, result in results:
                if not success:
                    failure_count += 1
            if failure_count:
                _exit_status = 1
            print >>sys.stderr, '  Failed to process', failure_count,\
                "responses"
        print >>sys.stderr, "  Peak virtual memory useage:", get_vmpeak()
        print >>sys.stderr, '  Remote CPU utilization:'
        cpu_util_info = calculate_remote_cpu_util(
            initial_wmiprvse_stats, final_wmiprvse_stats)
        print_remote_cpu_util(cpu_util_info)


class Config(object):

    def __init__(self, conn_infos=None):
        self.conn_infos = conn_infos


def _parse_remote(remote):
    url_parts = urlparse(remote)
    if url_parts.netloc:
        return url_parts.hostname, url_parts.scheme, url_parts.port
    return remote, DEFAULT_SCHEME, DEFAULT_PORT


def _parse_config_file(filename, utility):
    parser = RawConfigParser(allow_no_value=True)
    parser.read(filename)
    creds = {}
    index = dict(authentication=0, username=1)
    for key, value in parser.items('credentials'):
        k1, k2 = key.split('.')
        if k1 not in creds:
            creds[k1] = [None, None, None]
        creds[k1][index[k2]] = value
        if k2 == 'username':
            creds[k1][2] = getpass('{0} password ({1} credentials):'
                                   .format(value, k1))
    conn_infos = []
    for remote, cred_key in parser.items('remotes'):
        auth_type, username, password = creds[cred_key]
        hostname, scheme, port = _parse_remote(remote)
        conn_info = ConnectionInfo(
            hostname, auth_type, username, password, scheme, port)
        try:
            verify_conn_info(conn_info)
        except Exception as e:
            print >>sys.stderr, "ERROR: {0}".format(e)
            continue
        conn_infos.append(conn_info)
    config = Config(conn_infos)
    utility.add_config(parser, config)
    return config


def _parse_args(utility):
    parser = ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--config", "-c")
    parser.add_argument("--remote", "-r")
    parser.add_argument("--authentication", "-a", default='basic',
                        choices=['basic', 'kerberos'])
    parser.add_argument("--username", "-u")
    utility.add_args(parser)
    args = parser.parse_args()
    if not args.config:
        if not args.remote or not args.username:
            print >>sys.stderr, "ERROR: You must specify a config file with " \
                                "-c or specify remote and username"
            sys.exit(1)
        if not utility.check_args(args):
            sys.exit(1)
        if args.remote:
            hostname, scheme, port = _parse_remote(args.remote)
            password = getpass()
            args.conn_info = ConnectionInfo(
                hostname, args.authentication, args.username, password, scheme,
                port)
            try:
                verify_conn_info(args.conn_info)
            except Exception as e:
                print >>sys.stderr, "ERROR: {0}".format(e)
                sys.exit(1)
    for attr in 'remote', 'authentication', 'username':
        delattr(args, attr)
    return args


def _adapt_args_to_config(args, utility):
    config = Config([args.conn_info])
    utility.adapt_args_to_config(args, config)
    return config


def main(utility):
    args = _parse_args(utility)
    if args.debug:
        log.setLevel(level=logging.DEBUG)
        defer.setDebugging(True)
    if args.config:
        config = _parse_config_file(args.config, utility)
    else:
        config = _adapt_args_to_config(args, utility)
    reactor.callWhenRunning(utility.tx_main, args, config)
    reactor.run()
    sys.exit(_exit_status)


def stop_reactor(*args, **kwargs):
    if reactor.running:
        reactor.stop()
