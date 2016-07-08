#!/usr/bin/env python
##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject
from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.FileSystems import (
    guess_block_size,
    win32_mapped_logicaldisk_mount,
    win32_logicaldisk_mount,
    Win32_volume_mount,
    FileSystems
)
from Products.ZenTestCase.BaseTestCase import BaseTestCase


class DiskObject1(StringAttributeObject):
    def __init__(self):
        for i in ("DriveType", "MediaType", "BlockSize", "Size",
                  "Capacity", "MaximumComponentLength"):
            setattr(self, i, 100)
        setattr(self, "FreeSpace", 10)


class DiskObject2(StringAttributeObject):
    # test for missing data in FreeSpace and/or Size (ZEN-21351)
    # these should not be added to the map
    def __init__(self):
        for i in ("DriveType", "MediaType", "BlockSize",
                  "Capacity", "MaximumComponentLength"):
            setattr(self, i, 100)
        setattr(self, "Size", '')


class TestFileSystems(BaseTestCase):
    def setUp(self):
        self.plugin = FileSystems()

    def test_process(self):
        results = Mock(get=lambda *_: [DiskObject1(), DiskObject2()])
        data = self.plugin.process(StringAttributeObject(), results, Mock())
        self.assertEquals(len(data.maps), 4)
        d3 = data.maps[3]
        self.assertEquals(d3.blockSize, 100)
        self.assertEquals(d3.maxNameLen, 100)
        self.assertEquals(d3.drivetype, 'network drive')
        self.assertEquals(d3.mediatype, 'Fixed hard disk media')
        self.assertEquals(d3.mount, 'Name (Serial Number: VolumeSerialNumber) - VolumeName')
        self.assertEquals(d3.perfmonInstance, '\\LogicalDisk(Name)')
        self.assertEquals(d3.storageDevice, 'Name')
        self.assertEquals(d3.title, 'Name (Serial Number: VolumeSerialNumber) - VolumeName')
        self.assertEquals(d3.totalBlocks, 1)
        self.assertEquals(d3.totalFiles, 0)
        self.assertEquals(d3.type, 'FileSystem')


class TestHelpers(BaseTestCase):
    def test_Win32_volume_mount(self):
        self.assertEquals(Win32_volume_mount(StringAttributeObject()),
                          "Name (Serial Number: SerialNumber) - Label")

    def test_win32_logicaldisk_mount(self):
        self.assertEquals(win32_logicaldisk_mount(StringAttributeObject()),
                          "Name (Serial Number: VolumeSerialNumber) - VolumeName")

    def test_win32_mapped_logicaldisk_mount(self):
        self.assertEquals(win32_mapped_logicaldisk_mount(StringAttributeObject()),
                          "Name (Serial Number: VolumeSerialNumber) - VolumeName")

    def test_guess_block_size(self):
        self.assertEquals(guess_block_size(None), 4096)
        self.assertEquals(guess_block_size(1000), 512)


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    from utils import test_suite
    runner = Runner(found_suites=[test_suite((TestFileSystems, TestHelpers))])
    runner.run()
