##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Windows Processors (CPUs).

Models logical processors by querying Win32_Processor via WMI.
'''

from Products.DataCollector.plugins.zenoss.snmp.CpuMap import getManufacturerAndModel

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin


def int_or_none(value):
    '''
    Return value convert to int or None if not possible.
    '''
    try:
        return int(value)
    except Exception:
        return None


class CPUs(WinRMPlugin):
    compname = 'hw'
    relname = 'cpus'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.CPU'

    processor_attrs = (
        'DeviceID',
        'Description',
        'Manufacturer',
        'SocketDesignation',
        'CurrentClockSpeed',
        'ExtClock',
        'CurrentVoltage',
        'L2CacheSize',
        'Version',
        'NumberOfCores',
        'NumberOfLogicalProcessors',
        )

    cachememory_attrs = (
        'DeviceID',
        'InstalledSize',
        )

    wql_queries = {
        'Win32_Processor': "SELECT {} FROM Win32_Processor".format(', '.join(processor_attrs)),
        'Win32_CacheMemory': "SELECT {} FROM Win32_CacheMemory".format(', '.join(cachememory_attrs)),
        }

    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        l1_cache = None
        for cache in results['Win32_CacheMemory']:
            if cache.DeviceID == 'Cache Memory 0':
                l1_cache = int_or_none(cache.InstalledSize)
                break

        processor_id = 0

        rm = self.relMap()
        for socket, row in enumerate(results['Win32_Processor']):
            threads_per_core = (
                int(row.NumberOfLogicalProcessors) / int(row.NumberOfCores))

            for core in range(int(row.NumberOfCores)):
                for thread in range(threads_per_core):
                    name = 'CPU%s' % processor_id

                    product_key = getManufacturerAndModel(
                        '{} {}'.format(row.Manufacturer, row.Description))

                    current_voltage = int_or_none(row.CurrentVoltage)
                    if current_voltage:
                        current_voltage = current_voltage * 100

                    rm.append(self.objectMap({
                        'id': self.prepId(name),
                        'title': name,
                        'perfmonInstance': '\\Processor(%s)' % processor_id,
                        'setProductKey': product_key,
                        'socket': socket,
                        'core': core,
                        'thread': thread,
                        'clockspeed': int_or_none(row.CurrentClockSpeed),
                        'extspeed': int_or_none(row.ExtClock),
                        'voltage': current_voltage,
                        'cacheSizeL1': l1_cache,
                        'cacheSizeL2': int_or_none(row.L2CacheSize),
                        }))

                    processor_id += 1

        return rm
