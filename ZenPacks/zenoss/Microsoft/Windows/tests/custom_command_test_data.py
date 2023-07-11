#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2023, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from ZenPacks.zenoss.Microsoft.Windows.tests.ms_sql_always_on_test_data import ObjectFromDictProducer


class DummyCustomCommandStrategyResponse(ObjectFromDictProducer):

    def __init__(self):
        pass

    def get_custom_command_strategy_response_nagios_parser(self):
        preprocessing_data = {
            'response_data': {
                'exit_code': 2,
                'stderr': [],
                'stdout': [u'value:2']}
        }

        response = self.object_from_dict(preprocessing_data['response_data'])

        return response

    def get_custom_command_strategy_response_cacti_parser(self):
        preprocessing_data = {
            'response_data': {
                'exit_code': 2,
                'stderr': [],
                'stdout': [u'RabbitMQ has no issues on this node']}
        }

        response = self.object_from_dict(preprocessing_data['response_data'])

        return response

    def get_custom_command_strategy_response_json_parser(self):
        preprocessing_data = {
            'response_data': {
                'exit_code': 2,
                'stderr': [],
                'stdout': [u'{',
                            u'"events": [',
                            u'{',
                            u'"component":  "TestComponent",',
                            u'"device":  "10.88.122.71",',
                            u'"eventClass":  "/Win/Shell",',
                            u'"eventKey":  "ComponentError",',
                            u'"summary":  "Component reached size limit",',
                            u'"performanceData":  "",',
                            u'"severity":  4,',
                            u'"message":  "Component reached size limit"',
                            u'}',
                            u'],',
                            u'"values":  {',
                            u'"":  {',
                            u'"value":  2',
                            u'}',
                            u'}',
                            u'}']}
        }

        response = self.object_from_dict(preprocessing_data['response_data'])

        return response
