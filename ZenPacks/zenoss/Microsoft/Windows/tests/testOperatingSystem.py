##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock, patch
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject, load_pickle

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.OperatingSystem import OperatingSystem


class TestOperatingSystem(BaseTestCase):
    def setUp(self):
        self.plugin = OperatingSystem()
        self.device = StringAttributeObject()
        self.results = StringAttributeObject()
        self.results.MSCluster = ()
        self.results.Win32_SystemEnclosure = [StringAttributeObject()]
        self.results.Win32_ComputerSystem = [StringAttributeObject()]
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
