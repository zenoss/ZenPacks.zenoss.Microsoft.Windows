##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Windows Network Routes

Models network routes by querying Win32_IP4RouteTable via WMI.
'''

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import save


class Routes(WinRMPlugin):
    compname = 'os'
    relname = 'routes'
    modname = 'Products.ZenModel.IpRouteEntry'

    deviceProperties = WinRMPlugin.deviceProperties + (
        'zRouteMapCollectOnlyIndirect',
        'zRouteMapCollectOnlyLocal',
        'zRouteMapMaxRoutes',
        )

    queries = {
        'Win32_IP4RouteTable': "SELECT * FROM Win32_IP4RouteTable",
        }

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        rm = self.relMap()

        only_indirect = getattr(device, 'zRouteMapCollectOnlyIndirect', False)
        only_local = getattr(device, 'zRouteMapCollectOnlyLocal', False)
        max_routes = getattr(device, 'zRouteMapMaxRoutes', None)

        total_routes = 0

        for route in results.get('Win32_IP4RouteTable', ()):
            routemask_bits = self.maskToBits(route.Mask)
            protocol = lookup_protocol(route.Protocol or 0)
            rtype = lookup_type(route.Type or 0)

            if routemask_bits == 32:
                continue

            if only_local and protocol not in ('local', 'netmgmt'):
                continue

            if only_indirect and rtype != 'indirect':
                continue

            target = '{}/{}'.format(route.Destination, routemask_bits)

            rm.append(self.objectMap({
                'id': self.prepId(target),
                'title': target,
                'routemask': routemask_bits,
                'routeproto': protocol,
                'routetype': rtype,
                'metric1': route.Metric1,
                'metric2': route.Metric2,
                'metric3': route.Metric3,
                'metric4': route.Metric4,
                'metric5': route.Metric5,
                'setTarget': target,
                'setInterfaceIndex': route.InterfaceIndex,
                'setNextHopIp': route.NextHop,
                }))

            total_routes += 1

            if total_routes is not None:
                if total_routes >= max_routes:
                    log.warn(
                        "Modeled zRouteMapMaxRoutes (%s) on %s",
                        max_routes, device.id)

                    break

        return rm


def lookup_protocol(value):
    '''
    Return string representation of Win32_IP4RouteTable.Protocol.
    '''
    return {
        1: 'other',
        2: 'local',
        3: 'netmgmt',
        4: 'ICMP',
        5: 'EGP',
        6: 'GGP',
        7: 'hello',
        8: 'RIP',
        9: 'IS-IS',
        10: 'ES-IS',
        11: 'Cisco LGRP',
        12: 'bbnSpflgp',
        13: 'OSPF',
        14: 'BGP',
        }.get(int(value), 'unknown')


def lookup_type(value):
    '''
    Return string representation of Win32_IP4RouteTable.Type.
    '''
    return {
        1: 'other',
        2: 'invalid',
        3: 'direct',
        4: 'indirect',
        }.get(int(value), 'unknown')
