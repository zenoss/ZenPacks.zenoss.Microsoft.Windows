##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

# stdlib imports
import copy

import Globals  # noqa
from Products.ZenUtils.Utils import unused
from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.ZenPackLib import zenpacklib
# ZenPack imports
from ZenPacks.zenoss.Microsoft.Windows import ZenPack
from ZenPacks.zenoss.Microsoft.Windows.OperatingSystem import OperatingSystem
from ZenPacks.zenoss.Microsoft.Windows.migrate.AddOSRelations import AddOSRelations

# Local testing imports
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import create_device

unused(Globals)


class migrateTests(BaseTestCase):
    """Tests for AddOSRelations.migrate()."""

    def afterSetUp(self):
        super(migrateTests, self).afterSetUp()

        pack = ZenPack("ZenPacks.zenoss.Microsoft.Windows")
        packs = self.dmd.ZenPackManager.packs
        packs._setObject(pack.id, pack)
        self.pack = packs._getOb(pack.id)
        self.step = AddOSRelations()

    def test_needed(self):
        """Test that migration works when it is needed."""
        original_relations = copy.copy(OperatingSystem._relations)

        # Remove the new relations from OperatingSystem. This will allow the
        # following device creation to simulate how the device and it's os
        # would have been created in versions before 2.5.0.
        OperatingSystem._relations = tuple(
            x for x in OperatingSystem._relations
            if x[0] not in ("clusternodes", "clusternetworks"))

        try:
            device = create_device(
                dmd=self.dmd,
                zPythonClass="ZenPacks.zenoss.Microsoft.Windows.Device",
                device_id="test-windows1",
                datamaps=[])
        finally:
            # Restore OperatingSystem._relations to its original value to avoid
            # interfering with other tests.
            OperatingSystem._relations = original_relations

        os = device.os

        # Make sure our test is setup properly.
        self.assertFalse(
            os.aqBaseHasAttr("clusternodes") or os.aqBaseHasAttr("clusternetworks"),
            "{}.os has clusternodes or clusternetworks relationships before migrate"
            .format(device.id))

        self.step.migrate(self.pack)

        # Validate that the relationships were created.
        self.assertTrue(
            os.aqBaseHasAttr("clusternodes") and os.aqBaseHasAttr("clusternetworks"),
            "{}.os is missing clusternodes or clusternetworks relationship(s) after migrate"
            .format(device.id))

        # Validate that the relationship methods return iterables.
        len(os.clusternodes() + os.clusternetworks())

    def test_unneeded(self):
        """Test the migration doesn't fail with it isn't needed."""
        device = create_device(
            dmd=self.dmd,
            zPythonClass="ZenPacks.zenoss.Microsoft.Windows.Device",
            device_id="test-windows1",
            datamaps=[])

        os = device.os

        # Make sure our test is setup properly.
        self.assertTrue(
            os.aqBaseHasAttr("clusternodes") and os.aqBaseHasAttr("clusternetworks"),
            "{}.os is missing clusternodes or clusternetworks relationship(s) before migrate"
            .format(device.id))

        self.step.migrate(self.pack)

        # Validate that the relationships were created.
        self.assertTrue(
            os.aqBaseHasAttr("clusternodes") and os.aqBaseHasAttr("clusternetworks"),
            "{}.os is missing clusternodes or clusternetworks relationship(s) after migrate"
            .format(device.id))

        # Validate that the relationship methods return iterables.
        len(os.clusternodes() + os.clusternetworks())


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(migrateTests))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
