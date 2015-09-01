##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from itertools import repeat

from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import sentinel
from ZenPacks.zenoss.Microsoft.Windows.datasources.PerfmonDataSource import (
    format_stdout,
    format_counters,
    convert_to_ps_counter,
    DataPersister,
)


class TestDataPersister(BaseTestCase):
    def setUp(self):
        self.dp = DataPersister()
        self.dp.touch(sentinel.device0)

    def test_maintenance(self):
        self.dp.devices[sentinel.device0]['last'] = 0
        self.dp.maintenance()
        self.assertEquals(len(self.dp.devices), 0)

    def test_touch(self):
        for _ in repeat(None, 2):
            self.dp.touch(sentinel.device1)
            self.assertEquals(len(self.dp.devices), 2)

    def test_get(self):
        device = self.dp.get(sentinel.device0)
        self.assertEquals(device['maps'], [])

    def test_remove(self):
        self.dp.remove(sentinel.device0)
        self.assertEquals(len(self.dp.devices), 0)

    def test_add_event(self):
        self.dp.add_event(sentinel.device0, sentinel.event0)
        self.assertEquals(len(self.dp.devices[sentinel.device0]['events']), 1)

    def test_add_value(self):
        self.dp.add_value(sentinel.device0,
                          sentinel.component0,
                          sentinel.datasource0,
                          sentinel.value0,
                          sentinel.collect_time0)
        self.assertEquals(self.dp.devices[sentinel.device0]['values']
                          [sentinel.component0][sentinel.datasource0],
                          (sentinel.value0, sentinel.collect_time0))

    def test_pop(self):
        d0 = self.dp.pop(sentinel.device0)
        self.assertEquals(d0['maps'], [])
        self.assertEquals(len(self.dp.devices), 0)


class TestConvert_to_ps_counter(BaseTestCase):
    def test_convert_to_ps_counter(self):
        self.assertEquals(convert_to_ps_counter("counter"), "counter")
        self.assertEquals(convert_to_ps_counter(
            u"\u0444(\u0444)".decode()
        ), "\\u0444('+[char]0x0444+')")


class TestFormat_counters(BaseTestCase):
    def test_format_counters(self):
        self.assertEquals(format_counters(['a', 'b']), "('a'),('b')")


class TestFormat_stdout(BaseTestCase):
    def test_format_stdout(self):
        self.assertEquals(format_stdout([]), ([], False))
        self.assertEquals(format_stdout(["Readings : "]), ([""], True))
