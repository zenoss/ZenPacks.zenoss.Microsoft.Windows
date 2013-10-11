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

Models running processes by querying Win32_Process via WMI.
'''

import re

from Products.ZenModel import OSProcess
from Products.ZenUtils.Utils import prepId

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import get_processText


class Processes(WinRMPlugin):
    compname = 'os'
    relname = 'processes'
    modname = 'Products.ZenModel.OSProcess'

    deviceProperties = WinRMPlugin.deviceProperties + (
        'getOSProcessMatchers',
        )

    wql_queries = [
        "SELECT Name, ExecutablePath, CommandLine FROM Win32_Process",
        ]

    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        self.compile_regexes(device, log)

        seen = set()

        rm = self.relMap()

        for item in results.values()[0]:
            procName = item.ExecutablePath or item.Name
            if item.CommandLine:
                item.CommandLine = item.CommandLine.strip('"')
                parameters = item.CommandLine.replace(
                    procName, '', 1).strip()
            else:
                parameters = ''

            processText = get_processText(item)

            for matcher in device.getOSProcessMatchers:
                if hasattr(OSProcess.OSProcess, 'matchRegex'):
                    match = OSProcess.OSProcess.matchRegex(
                        matcher['regex'],
                        matcher['excludeRegex'],
                        processText)
                else:
                    match = matcher['regex'].search(processText)

                if not match:
                    continue

                if hasattr(OSProcess.OSProcess, 'generateId'):
                    process_id = OSProcess.OSProcess.generateId(
                        matcher['regex'],
                        matcher['getPrimaryUrlPath'],
                        processText)
                else:
                    process_id = prepId(OSProcess.getProcessIdentifier(
                        procName,
                        None if matcher['ignoreParameters'] else parameters))

                if process_id in seen:
                    continue

                seen.add(process_id)

                data = {
                    'id': process_id,
                    'procName': procName,
                    'parameters': parameters,
                    'setOSProcessClass': matcher['getPrimaryDmdId'],
                    }

                if hasattr(OSProcess.OSProcess, 'processText'):
                    data['processText'] = processText

                rm.append(self.objectMap(data))

        return rm

    def compile_regexes(self, device, log):
        for matcher in device.getOSProcessMatchers:
            try:
                matcher['regex'] = re.compile(matcher['regex'])
            except Exception:
                log.warning(
                    "Invalid process regex '%s' -- ignoring",
                    matcher['regex'])

            if 'excludeRegex' in matcher:
                try:
                    matcher['excludeRegex'] = re.compile(
                        matcher['excludeRegex'])

                except Exception:
                    log.warning(
                        "Invalid process exclude regex '%s' -- ignoring",
                        matcher['excludeRegex'])
