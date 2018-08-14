#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
# Zenoss Imports
import Globals  # noqa
from Products.ZenUtils.Utils import unused
unused(Globals)

from mock import Mock, sentinel

from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject, load_pickle, load_pickle_file

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.Interfaces import (
    Interfaces,
    filter_maps,
)


class TestInterfaces(BaseTestCase):
    def setUp(self):
        self.results = load_pickle(self, 'results')
        self.results['win32_pnpentity'] = {'Win32_PnPEntity': {'12': self.results['Win32_NetworkAdapter']}}
        self.device = load_pickle(self, 'device')
        self.plugin = Interfaces()

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(len(data.maps), 13)
        eth0 = data.maps[12]
        self.assertEquals(eth0.adminStatus, 1)
        self.assertEquals(eth0.description, "Local Area Connection 2")
        self.assertEquals(eth0.duplex, 0)
        self.assertEquals(eth0.id, "12-Intel_R_ PRO_1000 MT Network Connection")
        self.assertEquals(eth0.ifindex, '14')
        self.assertEquals(eth0.interfaceName, "Intel(R) PRO/1000 MT Network Connection")
        self.assertEquals(eth0.macaddress, "00:50:56:8D:45:FC")
        self.assertEquals(eth0.perfmonInstance, '\\Network Interface(WAN Miniport [SSTP])')
        self.assertEquals(eth0.setIpAddresses, ['192.168.240.37/23', 'fe80::a930:96ad:f65e:b3ba/64'])
        self.assertEquals(eth0.speed, 1000000000)
        self.assertEquals(eth0.title, "Intel(R) PRO/1000 MT Network Connection")
        self.assertEquals(eth0.type, "Ethernet 802.3")

    def test_sanitize_counters(self):
        counters = Mock()
        counters.stdout = "a:None|a:a|"
        self.assertIsNone(self.plugin.sanitize_counters(None))
        self.assertEquals(self.plugin.sanitize_counters(counters), {'a': 'a'})


class TestHelpers(BaseTestCase):
    def test_filter_maps(self):
        om0 = StringAttributeObject()
        om1 = StringAttributeObject()
        om2 = StringAttributeObject()

        device = StringAttributeObject()
        for objectmap, attribute, prop in zip(
                (om0, om1, om2),
                ('description', 'interfaceName', 'type'),
                ('zInterfaceMapIgnoreDescriptions', 'zInterfaceMapIgnoreNames', 'zInterfaceMapIgnoreTypes')
        ):
            setattr(objectmap, attribute, 'ignore')
            setattr(device, prop, 'ignore')

        self.assertFalse(list(filter_maps([om0, om1, om2], device, Mock())))


class TestInterfacesCounters(BaseTestCase):
    def setUp(self):
        self.results = load_pickle(self, 'interfaces')[0]
        self.device = load_pickle(self, 'device')
        self.plugin = Interfaces()

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(len(data.maps), 14)

        self.assertFalse(hasattr(data.maps[7], 'perfmonInstance'))
        self.assertEquals(data.maps[12].perfmonInstance, "\\Network Interface(RedHat PV NIC Driver _2)")
        results = load_pickle_file(self, 'Interfaces_process_163512')[0]
        for i in results['Win32_NetworkAdapter']:
            i.PhysicalAdapter = 'false'
        data = self.plugin.process(self.device, results, Mock())
        self.assertEquals(data.maps[7].perfmonInstance, "\\Network Interface(AWS PV Network Device _0)")


class TestTeamInterfaces(BaseTestCase):
    def setUp(self):
        self.device = load_pickle_file(self, 'device')
        self.plugin = Interfaces()

    def test_process(self):
        self.results = load_pickle_file(self, 'Interfaces_process_184038')[0]
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data.maps[7].perfmonInstance, "\\Network Interface(HP NC382i DP Multifunction Gigabit Server Adapter)")
        self.assertEquals(data.maps[8].perfmonInstance, "\\Network Interface(HP NC382i DP Multifunction Gigabit Server Adapter _2)")
        self.assertEquals(data.maps[13].perfmonInstance, "\\Network Interface(HP NC382i DP Multifunction Gigabit Server Adapter#1)")
        self.assertEquals(data.maps[14].perfmonInstance, "\\Network Interface(HP NC382i DP Multifunction Gigabit Server Adapter _2#1)")
        self.results = load_pickle_file(self, 'Interfaces_process_184151')[0]
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data.maps[7].perfmonInstance, "\\Network Interface(HP NC382i DP Multifunction Gigabit Server Adapter)")
        self.assertEquals(data.maps[8].perfmonInstance, "\\Network Interface(HP NC382i DP Multifunction Gigabit Server Adapter _2)")
        self.assertEquals(data.maps[12].perfmonInstance, "\\Network Interface(HP NC382i DP Multifunction Gigabit Server Adapter#1)")
        self.assertEquals(data.maps[13].perfmonInstance, "\\Network Interface(HP NC382i DP Multifunction Gigabit Server Adapter _2#1)")


class TestNoWMI(BaseTestCase):
    """Test case for no WMI data, but there was successful powershell collection"""
    def setUp(self):
        self.results = load_pickle_file(self, 'Interfaces_process_194131')[0]
        self.device = load_pickle_file(self, 'device')
        self.plugin = Interfaces()

    def test_process(self):
        m = Mock()
        data = self.plugin.process(self.device, self.results, m)
        # We should not return an empty relationship map
        self.assertEquals(data, None)
        self.assertTrue('Received incomplete Interface modeling results.' in str(m.mock_calls[1]))


class TestZPS3902(BaseTestCase):
    """Test case for output from 2016 server.  counters2012 should have output"""
    def setUp(self):
        # pickled results from a 2016 server
        self.results = load_pickle_file(self, 'Interfaces_process_215200')[0]

    def test_counters2012(self):
        has_counters = True if self.results['counters2012'].stdout else False
        self.assertTrue(has_counters)


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestNoWMI))
    suite.addTest(makeSuite(TestInterfaces))
    suite.addTest(makeSuite(TestHelpers))
    suite.addTest(makeSuite(TestInterfacesCounters))
    suite.addTest(makeSuite(TestTeamInterfaces))
    suite.addTest(makeSuite(TestZPS3902))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
