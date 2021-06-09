##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Windows Running Processes

Models running processes by querying Win32_Process and
Win32_PerfFormattedData_PerfProc_Process via WMI.
'''

import re

from itertools import ifilter, imap

from Products.ZenModel import OSProcess
from Products.ZenModel.Device import Device
from Products.ZenUtils.Utils import prepId

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import (
    get_processNameAndArgs,
    get_processText,
    save
    )

try:
    # Introduced in Zenoss 4.2 2013-10-15 RPS.
    from Products.ZenModel.OSProcessMatcher import buildObjectMapData
except ImportError:
    def buildObjectMapData(processClassMatchData, lines):
        raise Exception("buildObjectMapData does not exist on this Zenoss")
        return []


# Introduced in Zenoss 4.2 2013-10-15 RPS.
PROXY_MATCH_PROPERTY = 'osProcessClassMatchData'


class Processes(WinRMPlugin):
    compname = 'os'
    relname = 'processes'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.OSProcess'

    deviceProperties = WinRMPlugin.deviceProperties + (
        PROXY_MATCH_PROPERTY,
        )

    queries = {
        'Win32_Process': "SELECT Name, ExecutablePath, CommandLine FROM Win32_Process",
        'Win32_PerfFormattedData_PerfProc_Process': "SELECT * FROM Win32_PerfFormattedData_PerfProc_Process",
        }

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        rm = self.relMap()

        # Get process ObjectMap instances.
        oms = self.new_process(device, results, log)

        # Determine if WorkingSetPrivate is supported.
        try:
            perfproc = results.get('Win32_PerfFormattedData_PerfProc_Process', (None,))[0]
            supports_WorkingSetPrivate = hasattr(perfproc, 'WorkingSetPrivate')
        except IndexError:
            supports_WorkingSetPrivate = False

        for om in oms:
            om.supports_WorkingSetPrivate = supports_WorkingSetPrivate
            rm.append(om)

        return rm

    def new_process(self, device, results, log):
        '''
        Model processes according to new style.

        Handles style introduced by Zenoss 4.2 2013-10-15 RPS.
        '''
        processes = ifilter(bool, imap(get_processText, results.values()[0]))
        matchers = device.osProcessClassMatchData if hasattr(device, "osProcessClassMatchData") else []
        #log.info("getting process matchers...", matchers)
        oms = imap(
            self.objectMap,
            buildObjectMapData(matchers, processes))

        for om in oms:
            yield om

