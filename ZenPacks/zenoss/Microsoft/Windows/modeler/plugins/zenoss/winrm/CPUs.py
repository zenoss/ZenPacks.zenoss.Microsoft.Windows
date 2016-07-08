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

import re

from Products.DataCollector.plugins.zenoss.snmp.CpuMap import \
    getManufacturerAndModel

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import save


def int_or_none(value):
    '''
    Return value convert to int or None if not possible.
    '''
    try:
        return int(value)
    except Exception:
        return None


def check_value(value):
    '''
    Return value or None
    '''
    return value if value else None


class CPUs(WinRMPlugin):
    compname = 'hw'
    relname = 'cpus'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.CPU'

    cachememory_attrs = (
        'DeviceID',
        'InstalledSize',
    )

    queries = {
        'Win32_Processor': 'SELECT * FROM Win32_Processor',
        'Win32_CacheMemory': "SELECT {} FROM Win32_CacheMemory".format(
            ', '.join(cachememory_attrs)
        ),
    }

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        for cache in results.get('Win32_CacheMemory', []):
            if cache.DeviceID == 'Cache Memory 0':
                l1_cache_size = int_or_none(cache.InstalledSize)
                break
        else:
            l1_cache_size = None

        rm = self.relMap()
        for processor in results.get('Win32_Processor', []):
            product_key = getManufacturerAndModel(
                ', '.join((processor.Name, processor.Version)))

            socket = None
            if processor.SocketDesignation:
                socket_match = re.search(r'(\d+)', processor.SocketDesignation)
                if socket_match:
                    socket = int_or_none(socket_match.group(1))

            # Not available in Windows 2003 or XP.
            cores = int_or_none(getattr(processor, 'NumberOfCores', None))
            threads = int_or_none(
                getattr(processor, 'NumberOfLogicalProcessors', None)
            )
            l3_cache_size = int_or_none(
                getattr(processor, 'L3CacheSize', None)
            )
            l3_cache_speed = int_or_none(
                getattr(processor, 'L3CacheSpeed', None)
            )

            current_voltage = int_or_none(processor.CurrentVoltage)
            if current_voltage:
                current_voltage = current_voltage * 100

            rm.append(self.objectMap({
                'id': self.prepId(processor.DeviceID),
                'title': processor.Name,
                'description': processor.Description,
                'perfmonInstance': self.getPerfmonInstance(processor, log),
                'setProductKey': product_key,
                'socket': socket,
                'cores': cores,
                'threads': threads,
                'clockspeed': int_or_none(processor.CurrentClockSpeed),
                'extspeed': int_or_none(processor.ExtClock),
                'voltage': current_voltage,
                'cacheSizeL1': check_value(l1_cache_size),
                'cacheSizeL2': check_value(int_or_none(processor.L2CacheSize)),
                'cacheSpeedL2': check_value(
                    int_or_none(processor.L2CacheSpeed)
                ),
                'cacheSizeL3': check_value(l3_cache_size),
                'cacheSpeedL3': check_value(l3_cache_speed),
            }))
        return rm

    def getPerfmonInstance(self, processor, log):
        '''
        Return perfmonInstance for processor.
        '''
        try:
            return '\\Processor(%d)' % int(processor.DeviceID.split('CPU')[1])
        except (IndexError, ValueError):
            log.warn(
                "CPU DeviceID property ('%s') malformed, perfmon monitoring "
                "will be skipped", processor.deviceid)
