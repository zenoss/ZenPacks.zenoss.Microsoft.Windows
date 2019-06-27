##############################################################################
#
# Copyright (C) Zenoss, Inc. 2019, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.DataCollector.plugins.DataMaps import ObjectMap, RelationshipMap

try:
    from ZenPacks.zenoss.DynamicView.tests import DynamicViewTestCase
except ImportError:
    import unittest

    @unittest.skip("tests require DynamicView >= 1.7.0")
    class DynamicViewTestCase(unittest.TestCase):
        """TestCase stub if DynamicViewTestCase isn't available."""


# TODO: Complete this sometime. Right now, something is better than nothing.
EXPECTED_IMPACTS = """
[windows1]->[windows1/nic1]
[windows1]->[windows1/service1]
"""

DATAMAPS = [
    RelationshipMap(
        modname="ZenPacks.zenoss.Microsoft.Windows.Interface",
        compname="os",
        relname="interfaces",
        objmaps=[ObjectMap({"id": "nic1"})]),

    RelationshipMap(
        modname="ZenPacks.zenoss.Microsoft.Windows.WinService",
        compname="os",
        relname="winservices",
        objmaps=[ObjectMap({"id": "service1"})]),
]


class DynamicViewTests(DynamicViewTestCase):
    """DynamicView tests."""

    # ZenPacks to initialize for testing purposes.
    zenpacks = [
        "ZenPacks.zenoss.Microsoft.Windows",
    ]

    # Expected impact relationships.
    expected_impacts = EXPECTED_IMPACTS

    # Devices to create.
    device_data = {
        "windows1": {
            "deviceClass": "/Server/Microsoft/Windows",
            "zPythonClass": "ZenPacks.zenoss.Microsoft.Windows.Device",
            "dataMaps": DATAMAPS,
        },
    }

    def test_impacts(self):
        self.check_impacts()
