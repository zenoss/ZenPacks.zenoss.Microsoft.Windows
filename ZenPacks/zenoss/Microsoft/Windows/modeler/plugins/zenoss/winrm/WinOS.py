##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Windows Operating System Collection

"""

from twisted.internet import reactor
from twisted.web.client import Agent
from twisted.internet.defer import DeferredList

from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import addLocalLibPath

addLocalLibPath()

from txwinrm.txwinrm2 import WinrmClient


class WinOS(PythonPlugin):

    deviceProperties = PythonPlugin.deviceProperties + (
        'zWinUser',
        'zWinPassword',
        )

    WinRMQueries = [
        'select * from Win32_logicaldisk',
        'select * from Win32_Volume',
        'select * from Win32_OperatingSystem',
        'select * from Win32_SystemEnclosure',
        'select * from Win32_ComputerSystem',
        ]

    def collect(self, device, log):

        import pdb; pdb.set_trace()
        username = device.zWinUser
        password = device.zWinPassword
        hostname = device.manageIp

        client = WinrmClient(username, password, hostname)
        agent = Agent(reactor)

        deferreds = []

        for wql in self.WinRMQueries:
            txcall = client.enumerate(wql)

            d = agent.request(
                'POST',
                txcall['url'],
                txcall['headers'],
                txcall['body'])

            deferreds.append(d)

        dl = DeferredList(deferreds, consumeErrors=True)
        import pdb; pdb.set_trace()

        return dl

    def process(self, device, results, log):

        import pdb; pdb.set_trace()

        log.info('Modeler %s processing data for device %s',
            self.name(), device.id)
