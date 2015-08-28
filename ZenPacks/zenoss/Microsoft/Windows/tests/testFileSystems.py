##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject
from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.FileSystems import (
    guess_block_size,
    win32_mapped_logicaldisk_mount,
    win32_logicaldisk_mount,
    Win32_volume_mount,
    FileSystems
)


class DiskObject(StringAttributeObject):
    def __init__(self):
        for i in ("DriveType", "MediaType", "BlockSize", "Size",
                  "Capacity", "MaximumComponentLength"):
            setattr(self, i, 100)


class TestFileSystems(BaseTestCase):
    def setUp(self):
        self.plugin = FileSystems()

    def test_process(self):
        results = Mock(get=lambda *_: [DiskObject()])
        data = self.plugin.process(StringAttributeObject(), results, Mock())
        self.assertEquals(len(data.maps), 3)
        d2 = data.maps[2]
        self.assertEquals(d2.blockSize, 100)
        self.assertEquals(d2.maxNameLen, 100)
        self.assertEquals(d2.drivetype, 'network drive')
        self.assertEquals(d2.mediatype, 'Fixed hard disk media')
        self.assertEquals(d2.mount, 'Name (Serial Number: VolumeSerialNumber) - VolumeName')
        self.assertEquals(d2.perfmonInstance, '\\LogicalDisk(Name)')
        self.assertEquals(d2.storageDevice, 'Name')
        self.assertEquals(d2.title, 'Name (Serial Number: VolumeSerialNumber) - VolumeName')
        self.assertEquals(d2.totalBlocks, 1)
        self.assertEquals(d2.totalFiles, 0)
        self.assertEquals(d2.type, 'FileSystem')


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
