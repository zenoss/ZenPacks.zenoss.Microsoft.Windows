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

from Products.ZenModel.OSProcess import OSProcess, getProcessIdentifier
from Products.ZenUtils.Utils import prepId

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin


# Process monitoring changed significantly in Zenoss 4.2.4. We want to
# support the new and old ways.
NEW_STYLE = hasattr(OSProcess, 'processText')


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

            processText = item.CommandLine or item.ExecutablePath or item.Name

            for matcher in device.getOSProcessMatchers:
                if NEW_STYLE:
                    match = OSProcess.matchRegex(
                        matcher['regex'],
                        matcher['excludeRegex'],
                        processText)
                else:
                    match = matcher['regex'].search(processText)

                if not match:
                    continue

                if NEW_STYLE:
                    process_id = OSProcess.generateId(
                        matcher['regex'],
                        matcher['getPrimaryUrlPath'],
                        processText)
                else:
                    process_id = prepId(getProcessIdentifier(
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

                if NEW_STYLE:
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

            # Only NEW_STYLE matchers have the excludeRegex key.
            if not NEW_STYLE:
                continue

            try:
                matcher['excludeRegex'] = re.compile(matcher['excludeRegex'])
            except Exception:
                log.warning(
                    "Invalid process exclude regex '%s' -- ignoring",
                    matcher['excludeRegex'])
