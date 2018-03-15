#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import Globals

from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock, patch
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject, load_pickle, load_pickle_file

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.OperatingSystem import OperatingSystem
from txwinrm.enumerate import ItemsAccumulator


class TestOperatingSystem(BaseTestCase):
    def setUp(self):
        self.plugin = OperatingSystem()
        self.device = StringAttributeObject()
        self.results = StringAttributeObject()
        self.results.MSCluster = ()
        self.results.Win32_SystemEnclosure = [StringAttributeObject()]
        self.results.Win32_ComputerSystem = [StringAttributeObject({'blah': 'blah'})]
        self.results.Win32_OperatingSystem = [StringAttributeObject()]
        self.results.exchange_version = Mock(stdout=['15'])
        self.results.ActiveDirectory = [StringAttributeObject()]
        for k in ('TotalVisibleMemorySize', 'TotalVirtualMemorySize'):
            setattr(self.results.Win32_OperatingSystem[0], k, 1)

    @patch('socket.gethostbyaddr', Mock(return_value=("FQDN", [], ["8.8.8.8"])))
    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data[0].ip_and_hostname, ['8.8.8.8', 'FQDN'])
        self.assertEquals(data[0].domain_controller, False)
        self.assertEquals(data[0].msexchangeversion, 'MSExchange2013IS')
        self.assertEquals(data[0].setClusterMachines, [])
        self.assertEquals(data[0].snmpContact, 'PrimaryOwnerName')
        self.assertEquals(data[0].snmpDescr, 'Caption')
        self.assertEquals(data[0].snmpSysName, 'Name')
        self.assertEquals(data[1].serialNumber, 'SerialNumber')
        self.assertEquals(data[1].tag, 'Tag')
        self.assertEquals(data[1].totalMemory, 1024)
        self.assertEquals(data[2].totalSwap, 1024)


class TestDomainController(BaseTestCase):
    '''
    Test if a device is a domain controller
    '''
    def setUp(self):
        self.plugin = OperatingSystem()
        self.device = load_pickle(self, 'device')
        self.results = load_pickle(self, 'results')

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data[0].domain_controller, True)


class TestEmptyWin32_ComputerSystem(BaseTestCase):
    """
    Test if a device is a domain controller
    """
    def setUp(self):
        self.plugin = OperatingSystem()
        self.device = StringAttributeObject()
        self.results = load_pickle_file(self, 'OperatingSystem_process_103136')[0]

    def test_process(self):
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertFalse(hasattr(self.results['Win32_ComputerSystem'][0], 'Name'))
        self.assertFalse(hasattr(self.results['Win32_ComputerSystem'][0], 'PrimaryOwnerName'))
        self.assertFalse(hasattr(self.results['Win32_ComputerSystem'][0], 'Caption'))
        self.assertFalse(hasattr(self.results['Win32_ComputerSystem'][0], 'DomainRole'))
        self.assertEquals(data[0].snmpDescr, 'Microsoft Windows Server 2016 Standard')
        self.assertEquals(data[0].snmpSysName, 'WIN2016-KDC-01')
        self.assertTrue(data[0].domain_controller)


class TestOddWMIClasses(BaseTestCase):
    '''
    Test if a device is a domain controller
    '''
    def setUp(self):
        self.plugin = OperatingSystem()
        self.device = StringAttributeObject()

    def test_empty_wmi_process(self):
        acc = ItemsAccumulator()
        acc.new_item()
        self.results = {'Win32_SystemEnclosure': acc.items,
                        'Win32_ComputerSystem': acc.items,
                        'Win32_OperatingSystem': acc.items,
                        'exchange_version': Mock(stdout=['15'])}
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data[0].snmpDescr, 'Unknown')
        self.assertEquals(data[0].snmpContact, 'Unknown')
        self.assertEquals(data[0].snmpSysName, 'Unknown')

        self.assertEquals(data[1].tag, 'Unknown')

    def test_contact_none_process(self):
        # ZPS-3227 test for situation where PrimaryOwnerName
        # of Win32_ComputerSystem is None
        acc = ItemsAccumulator()
        acc.new_item()
        cs_acc = ItemsAccumulator()
        cs_acc.new_item()
        cs_acc.add_property('Name', None)
        cs_acc.add_property('PrimaryOwnerName', None)
        cs_acc.add_property('Caption', None)
        cs_acc.add_property('Domain', 'domain')
        cs_acc.add_property('Model', 'model')
        cs_acc.add_property('Manufacturer', 'Microsoft')
        cs_acc.add_property('DomainRole', '0')
        os_acc = ItemsAccumulator()
        os_acc.new_item()
        os_acc.add_property('CSName', None)
        os_acc.add_property('RegisteredUser', None)
        os_acc.add_property('Caption', None)
        os_acc.add_property('ProductType', '0')
        os_acc.add_property('SerialNumber', 'model')
        os_acc.add_property('Manufacturer', 'Microsoft')
        os_acc.add_property('TotalVisibleMemorySize', '1')
        os_acc.add_property('TotalVirtualMemorySize', '1')
        os_acc.add_property('CSDVersion', '1')
        self.results = {'Win32_SystemEnclosure': acc.items,
                        'Win32_ComputerSystem': cs_acc.items,
                        'Win32_OperatingSystem': os_acc.items,
                        'exchange_version': Mock(stdout=['15'])}
        data = self.plugin.process(self.device, self.results, Mock())
        self.assertEquals(data[0].snmpDescr, 'Unknown')
        self.assertEquals(data[0].snmpContact, 'Unknown')
        self.assertEquals(data[0].snmpSysName, 'Unknown')


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestOddWMIClasses))
    suite.addTest(makeSuite(TestEmptyWin32_ComputerSystem))
    suite.addTest(makeSuite(TestDomainController))
    suite.addTest(makeSuite(TestOperatingSystem))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
