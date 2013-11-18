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


class Routes(WinRMPlugin):
    compname = 'os'
    relname = 'routes'
    modname = 'Products.ZenModel.IpRouteEntry'

    queries = {
        'Win32_IP4RouteTable': "SELECT * FROM Win32_IP4RouteTable",
        }

    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        rm = self.relMap()

        for route in results.get('Win32_IP4RouteTable', ()):
            if route.Mask == '32':
                continue

            routemask_bits = self.maskToBits(route.Mask)
            target = '{}/{}'.format(route.Destination, routemask_bits)

            rm.append(self.objectMap({
                'id': self.prepId(target),
                'title': target,
                'routemask': routemask_bits,
                'routeproto': lookup_protocol(route.Protocol or 0),
                'routetype': lookup_type(route.Type or 0),
                'metric1': route.Metric1,
                'metric2': route.Metric2,
                'metric3': route.Metric3,
                'metric4': route.Metric4,
                'metric5': route.Metric5,
                'setTarget': target,
                'setInterfaceIndex': route.setInterfaceIndex,
                'setNextHopIp': route.NextHop,
                }))

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
