#! /usr/bin/env python

##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Use twisted web client to enumerate/pull WQL query.
"""

import logging
import sys
from argparse import ArgumentParser
from twisted.internet import reactor, defer
from twisted.internet.error import TimeoutError
from . import client as client_module

DEBUG = False
GLOBAL_ELEMENT_COUNT = 0
exit_status = 0


def get_vmpeak():
    with open('/proc/self/status') as status:
        for line in status:
            key, value = line.split(None, 1)
            if key == 'VmPeak:':
                return value


class ElementPrinter(object):

    def __init__(self, hostname, wql):
        self._hostname = hostname
        self._wql = wql
        self._elems_with_text = []
        self._demarc = '-' * 4

    def new_instance(self):
        if self._elems_with_text:
            self._elems_with_text.append((self._demarc, ''))

    def append_element(self, uri, localname, text):
        global GLOBAL_ELEMENT_COUNT
        GLOBAL_ELEMENT_COUNT += 1
        self._elems_with_text.append((localname, text))

    def print_elements_with_text(self, result):
        print '\n', self._hostname, "==>", self._wql
        for tag, text in self._elems_with_text:
            if tag == self._demarc:
                print ' ', self._demarc
            else:
                print '  {0} = {1}'.format(tag, text)


class ProcessStatsAccumulator(object):

    def __init__(self):
        self.process_stats = []

    def new_instance(self):
        self.process_stats.append({})

    def append_element(self, uri, localname, text):
        if not uri and localname in ['Name', 'IDProcess',
                                     'PercentProcessorTime',
                                     'Timestamp_Sys100NS']:
            self.process_stats[-1][localname] = text


@defer.inlineCallbacks
def get_remote_process_stats(client, hostname, username, password):
    wql = 'select Name, IDProcess, PercentProcessorTime,' \
          'Timestamp_Sys100NS from Win32_PerfRawData_PerfProc_Process ' \
          'where name like "wmi%"'
    accumulator = ProcessStatsAccumulator()
    yield client.enumerate(hostname, username, password, wql, accumulator)
    defer.returnValue(accumulator.process_stats)


def calculate_remote_cpu_util(initial_stats, final_stats):
    for hostname, initial_stats_dicts in initial_stats.iteritems():
        final_stats_dicts = final_stats[hostname]
        print >>sys.stderr, "   ", hostname
        for initial_stats_dict in initial_stats_dicts:
            name = initial_stats_dict["Name"]
            pid = initial_stats_dict["IDProcess"]
            for final_stats_dict in final_stats_dicts:
                if pid == final_stats_dict["IDProcess"]:
                    break
            else:
                raise Exception("Could not find final process stats for "
                                + hostname + " " + pid)
            x1 = float(final_stats_dict['PercentProcessorTime'])
            x0 = float(initial_stats_dict['PercentProcessorTime'])
            y1 = float(final_stats_dict['Timestamp_Sys100NS'])
            y0 = float(initial_stats_dict['Timestamp_Sys100NS'])
            cpu_pct = (x1 - x0) / (y1 - y0)
            fmt = "      {cpu_pct:.2%} of CPU time used by {name} "\
                  "process with pid {pid}"
            print >>sys.stderr, fmt.format(hostname=hostname, cpu_pct=cpu_pct,
                                           name=name, pid=pid)


@defer.inlineCallbacks
def send_requests(client, config):
    global exit_status
    initial_wmiprvse_stats = {}
    good_hosts = []
    for hostname, (username, password) in config.hosts.iteritems():
        try:
            initial_wmiprvse_stats[hostname] = yield get_remote_process_stats(
                client, hostname, username, password)
            good_hosts.append((hostname, username, password))
        except client_module.Unauthorized:
            continue
        except TimeoutError:
            continue
    if not good_hosts:
        exit_status = 1
        reactor.stop()
        return
    ds = []
    for hostname, username, password in good_hosts:
        for wql in config.wqls:
            printer = ElementPrinter(hostname, wql)
            d = client.enumerate(hostname, username, password, wql, printer)
            d.addCallback(printer.print_elements_with_text)
            ds.append(d)
    dl = defer.DeferredList(ds, consumeErrors=True)

    @defer.inlineCallbacks
    def dl_callback(results):
        global exit_status
        final_wmiprvse_stats = {}
        for hostname, (username, password) in config.hosts.iteritems():
            final_wmiprvse_stats[hostname] = yield get_remote_process_stats(
                client, hostname, username, password)
        print >>sys.stderr, '\nSummary:'
        print >>sys.stderr, '  Connected to', len(good_hosts), 'of', \
                            len(config.hosts), 'hosts'
        print >>sys.stderr, "  Processed", GLOBAL_ELEMENT_COUNT, "elements"
        failure_count = 0
        for success, result in results:
            if not success:
                failure_count += 1
        if failure_count:
            exit_status = 1
        print >>sys.stderr, '  Failed to process', failure_count, "responses"
        print >>sys.stderr, "  Peak virtual memory useage:", get_vmpeak()
        print >>sys.stderr, '  Remote CPU utilization:'
        calculate_remote_cpu_util(initial_wmiprvse_stats, final_wmiprvse_stats)
        reactor.stop()

    dl.addCallback(dl_callback)


class ConsoleLogger(object):

    def isEnabledFor(self, level):
        return DEBUG or level > logging.INFO

    def error(self, message):
        print >>sys.stderr, "ERROR:", message

    def debug(self, message):
        print message


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--parser", "-p", default='sax',
                        choices=['cetree', 'etree', 'sax'])
    parser.add_argument("--debug", "-d", action="store_true")
    return parser.parse_args()


def main():
    global DEBUG
    args = parse_args()
    DEBUG = args.debug
    factory = client_module.WinrmClientFactory(ConsoleLogger())
    client = factory.create_winrm_client(args.parser)
    from . import config
    reactor.callWhenRunning(send_requests, client, config)
    reactor.run()
    sys.exit(exit_status)


if __name__ == '__main__':
    main()
