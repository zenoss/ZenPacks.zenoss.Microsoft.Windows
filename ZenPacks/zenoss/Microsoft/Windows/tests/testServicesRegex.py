##############################################################################
#
# Copyright (C) Zenoss, Inc. 2020, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.Services import omit_service, validate_modeling_regex
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock

class TestServicesRegex(BaseTestCase):

    def setUp(self):
        self.device = Mock()
        self.log = Mock()

    def test_model_service_model_simple(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = ['^App']
        model_list, ignore_list = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'AppServiceXMF', self.log)
        self.assertFalse(omit)

    def test_model_service_model_complex(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = ['ServiceM{2,5}']
        model_list, ignore_list = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'ServiceMM', self.log)
        self.assertFalse(omit)

    def test_model_service_ignore_simple(self):
        self.device.zWinServicesNotModeled = ['.*test$']
        self.device.zWinServicesModeled = []
        model_list, ignore_list = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'Someservicetest', self.log)
        self.assertTrue(omit)

    def test_model_service_ignore_complex(self):
        self.device.zWinServicesNotModeled = ['^.ervice[cf][^a].*']
        self.device.zWinServicesModeled = []
        model_list, ignore_list = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'Servicefnbb', self.log)
        self.assertTrue(omit)

    def test_model_service_model_and_ignore(self):
        self.device.zWinServicesNotModeled = ['.*pp.*']
        self.device.zWinServicesModeled = ['App.*']
        model_list, ignore_list = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'AppTest', self.log)
        self.assertTrue(omit)

    def test_model_service_multiple_model(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = ['App.*', 'ServiceEvent.*', '[0-9]Service.*']
        model_list, ignore_list = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, '3Servicetest', self.log)
        self.assertFalse(omit)

    def test_model_service_multiple_ignore(self):
        self.device.zWinServicesNotModeled = ['App.*', 'ServiceEvent.*', '[0-9]Service.*']
        self.device.zWinServicesModeled = []
        model_list, ignore_list = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'ServiceEvent.*App', self.log)
        self.assertTrue(omit)

    def test_model_service_empty(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = []
        model_list, ignore_list = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'A', self.log)
        self.assertFalse(omit)

    def test_model_service_multiply_values(self):
        self.device.zWinServicesNotModeled = ['Servicex.*']
        self.device.zWinServicesModeled = ['App.*', 'ServiceEvent.*', '[0-9]Service.*']
        model_list, ignore_list = validate_modeling_regex(self.device, self.log)
        input_services = [
            'Servicexx',
            'Servicextest',
            'Servicetest5',
            'NewServicex5',
            'AppServicex',
            'ApServicex',
            'ServiceEventTest',
            'ServiceTestEvent',
            '0Service',
            '00Service',
        ]
        expected = ['AppServicex', 'ServiceEventTest', '0Service']
        result = []
        for service in input_services:
            if not omit_service(model_list, ignore_list, service, self.log):
                result.append(service)
        self.assertEqual(sorted(result), sorted(expected))
