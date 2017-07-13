#! /usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from collections import namedtuple
import Globals  # noqa

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.utils import errorMsgCheck, generateClearAuthEvents


class DataSource(namedtuple('DataSource', ['plugin_classname', 'datasource'])):
    pass


class Config(namedtuple('Config', ['manageIp', 'id', 'datasources'])):
    pass


class TestErrorEvents(BaseTestCase):
    def setUp(self):
        datasources = DataSource('ZenPacks.zenoss.Microsoft.Windows.datasources.TestDataSource',
                                 'test_error_event')
        self.config = Config('10.10.10.10', 'windows_test', [datasources])

    def testErrorMsgCheck(self):
        events = []
        error = 'Password expired'
        errorMsgCheck(self.config, events, error)
        error = 'Check username and password'
        errorMsgCheck(self.config, events, error)
        error = 'kinit error getting initial credentials'
        errorMsgCheck(self.config, events, error)
        error = 'kinit error server not in database'
        errorMsgCheck(self.config, events, error)
        self.assertEquals(len(events), 4)
        generateClearAuthEvents(self.config, events)

        self.assertEquals(len(events), 6)
        event_class_keys = {0: 'AuthenticationFailure',
                            1: 'AuthenticationFailure',
                            2: 'KerberosFailure',
                            3: 'KerberosFailure',
                            4: 'AuthenticationSuccess',
                            5: 'KerberosSuccess', }
        for k, v in event_class_keys.items():
            self.assertEquals(events[k]['eventClassKey'], v)
            if k <= 3:
                self.assertEquals(events[k]['severity'], 4)
            else:
                self.assertEquals(events[k]['severity'], 0)
            self.assertTrue('eventClass' in events[k])
            self.assertRegexpMatches(events[k]['eventKey'], 'Kerberos|Authentication\|windows_test')


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestErrorEvents))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
