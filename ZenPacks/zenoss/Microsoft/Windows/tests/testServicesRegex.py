##############################################################################
#
# Copyright (C) Zenoss, Inc. 2020, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.Services import (omit_service,
                                                                                     validate_modeling_regex,
                                                                                     truncate_service_class)
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock

class TestServicesRegex(BaseTestCase):

    def setUp(self):
        self.device = Mock()
        self.log = Mock()

    def test_model_service_model_simple(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = ['^App']
        self.device.zWinServicesGroupedByClass = []
        model_list, ignore_list, _ = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'AppServiceXMF', self.log)
        self.assertFalse(omit)

    def test_model_service_model_complex(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = ['ServiceM{2,5}']
        self.device.zWinServicesGroupedByClass = []
        model_list, ignore_list, _ = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'ServiceMM', self.log)
        self.assertFalse(omit)

    def test_model_service_ignore_simple(self):
        self.device.zWinServicesNotModeled = ['.*test$']
        self.device.zWinServicesModeled = []
        self.device.zWinServicesGroupedByClass = []
        model_list, ignore_list, _ = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'Someservicetest', self.log)
        self.assertTrue(omit)

    def test_model_service_ignore_complex(self):
        self.device.zWinServicesNotModeled = ['^.ervice[cf][^a].*']
        self.device.zWinServicesModeled = []
        self.device.zWinServicesGroupedByClass = []
        model_list, ignore_list, _ = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'Servicefnbb', self.log)
        self.assertTrue(omit)

    def test_model_service_model_and_ignore(self):
        self.device.zWinServicesNotModeled = ['.*pp.*']
        self.device.zWinServicesModeled = ['App.*']
        self.device.zWinServicesGroupedByClass = []
        model_list, ignore_list, _ = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'AppTest', self.log)
        self.assertTrue(omit)

    def test_model_service_multiple_model(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = ['App.*', 'ServiceEvent.*', '[0-9]Service.*']
        self.device.zWinServicesGroupedByClass = []
        model_list, ignore_list, _ = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, '3Servicetest', self.log)
        self.assertFalse(omit)

    def test_model_service_multiple_ignore(self):
        self.device.zWinServicesNotModeled = ['App.*', 'ServiceEvent.*', '[0-9]Service.*']
        self.device.zWinServicesModeled = []
        self.device.zWinServicesGroupedByClass = []
        model_list, ignore_list, _ = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'ServiceEvent.*App', self.log)
        self.assertTrue(omit)

    def test_model_service_empty(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = []
        self.device.zWinServicesGroupedByClass = []
        model_list, ignore_list, _ = validate_modeling_regex(self.device, self.log)
        omit = omit_service(model_list, ignore_list, 'A', self.log)
        self.assertFalse(omit)

    def test_model_service_multiply_values(self):
        self.device.zWinServicesNotModeled = ['Servicex.*']
        self.device.zWinServicesModeled = ['App.*', 'ServiceEvent.*', '[0-9]Service.*']
        self.device.zWinServicesGroupedByClass = []
        model_list, ignore_list, _ = validate_modeling_regex(self.device, self.log)
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

    def test_model_service_grouped(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = []
        self.device.zWinServicesGroupedByClass = ['CDPUserSvc']
        _, _, group_list = validate_modeling_regex(self.device, self.log)
        service_class_name, service_class_caption = truncate_service_class(group_list, 'CDPUserSvc_123asdl', 'Contact Data_123asdl')
        self.assertEqual(service_class_name, 'CDPUserSvc')
        self.assertEqual(service_class_caption, 'Contact Data')

    def test_model_service_grouped_empty(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = []
        self.device.zWinServicesGroupedByClass = []
        _, _, group_list = validate_modeling_regex(self.device, self.log)
        service_class_name, service_class_caption = truncate_service_class(group_list, 'PimIndexMaintenanceSvc_aeff1234', 'Contact Data_aeff1234')
        self.assertEqual(service_class_name, 'PimIndexMaintenanceSvc_aeff1234')
        self.assertEqual(service_class_caption, 'Contact Data_aeff1234')

    def test_model_service_grouped_multiple_underscores(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = []
        self.device.zWinServicesGroupedByClass = ['Test_Windows_Service']
        _, _, group_list = validate_modeling_regex(self.device, self.log)
        service_class_name, service_class_caption = truncate_service_class(group_list,
                                                                           'Test_Windows_Service_aeff1234',
                                                                           'Test_Windows_Caption_aeff1234')
        self.assertEqual(service_class_name, 'Test_Windows_Service')
        self.assertEqual(service_class_caption, 'Test_Windows_Caption')

    def test_model_service_grouped_multiple(self):
        self.device.zWinServicesNotModeled = []
        self.device.zWinServicesModeled = []
        self.device.zWinServicesGroupedByClass = ['Pim_Index_Maintenance_Svc', 'CDPUserSvc', 'OneSyncSvc']
        _, _, group_list = validate_modeling_regex(self.device, self.log)
        result_dict_grouped = {}
        input_services = {
                        'Servicexx': 'Servicexx',
                        'NewServicex5': 'NewServicex5',
                        'AppServicex': 'AppServicex',
                        'OneSyncSvc_asdb123': 'OneSyncSvc_asdb123',
                        'CDPUserSvc_asd123': 'CDPUserSvc_asd123',
                        'Pim_Index_Maintenance_Svc_aeff1234': 'Contact_Data_aeff4',
                        '0Service_11a': '0Service Data Data',
                        '00Service_22sd': '00Service_22sd Data Data_22sd',
                        }
        expected_grouped = {
                            'Servicexx': 'Servicexx',
                            'NewServicex5': 'NewServicex5',
                            'AppServicex': 'AppServicex',
                            'OneSyncSvc': 'OneSyncSvc',
                            'CDPUserSvc': 'CDPUserSvc',
                            'Pim_Index_Maintenance_Svc': 'Contact_Data',
                            '0Service_11a': '0Service Data Data',
                            '00Service_22sd': '00Service_22sd Data Data_22sd',
                            }
        for service, service_class in input_services.iteritems():
            service_class_name, service_class_caption = truncate_service_class(group_list, service, service_class)
            result_dict_grouped[service_class_name] = service_class_caption
        self.assertEqual(sorted(result_dict_grouped), sorted(expected_grouped))
