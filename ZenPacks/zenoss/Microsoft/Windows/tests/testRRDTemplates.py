##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenTestCase.BaseTestCase import BaseTestCase


class TestMonitoringTemplates(BaseTestCase):
    def test_getRRDTemplates(self):
        dc = self.dmd.Devices.createOrganizer('/Server/Microsoft/Windows')
        dc.setZenProperty(
            'zPythonClass',
            'ZenPacks.zenoss.Microsoft.Windows.Device')

        dc.setZenProperty(
            'zDeviceTemplates',
            ['Device', 'IIS', 'Active Directory', 'MSExchangeIS'])

        dc.manage_addRRDTemplate('Active Directory')
        dc.manage_addRRDTemplate('Active Directory 2003')
        dc.manage_addRRDTemplate('MSExchangeIS')
        dc.manage_addRRDTemplate('MSExchange2010IS')
        dc.manage_addRRDTemplate('MSExchange2013IS')

        server = dc.createInstance('server')
        server.setPerformanceMonitor('localhost')
        server.setManageIp('127.0.0.0')
        server.setOSProductKey('Windows 2003')

        # Active Directory
        found_wrong, found_right = False, False
        ad_is_set = False
        for template in server.getRRDTemplates():
            if 'Active Directory' in template.id:
                ad_is_set = True
                if template.id == 'Active Directory':
                    found_wrong = True
                elif template.id == 'Active Directory 2003':
                    found_right = True

        if ad_is_set:
            self.assertFalse(
                found_wrong,
                "wrong 'Active Directory' template bound to server2003")

            self.assertTrue(
                found_right,
                "correct 'Active Directory 2003' template not bound to server2003")

        # Exchange
        server.msexchangeversion = 'MSExchangeIS'

        for template in server.getRRDTemplates():
            if 'MSExchange' in template.id:
                self.assertEquals(template.id, 'MSExchangeIS')

        # Exchange MSExchangeIS to MSExchange2010IS
        server.msexchangeversion = 'MSExchange2010IS'

        for template in server.getRRDTemplates():
            if 'MSExchange' in template.id:
                self.assertEquals(template.id, 'MSExchange2010IS')

        # Exchange MSExchangeIS to MSExchange2013IS
        server.msexchangeversion = 'MSExchange2013IS'

        for template in server.getRRDTemplates():
            if 'MSExchange' in template.id:
                self.assertEquals(template.id, 'MSExchange2013IS')


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestMonitoringTemplates))
    return suite
