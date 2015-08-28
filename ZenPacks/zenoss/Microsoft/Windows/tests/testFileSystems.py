##############################################################################
#
# Copyright (C) Zenoss, Inc. 2014, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from mock import Mock, sentinel, patch, MagicMock

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.FileSystems import (
    guess_block_size,
    win32_mapped_logicaldisk_mount,
    win32_logicaldisk_mount,
    Win32_volume_mount
)


class TestFileSystems(BaseTestCase):
    def setUp(self):
        pass

    def test_process(self):
        pass


class MockedDisk(Mock):
    def __init__(self):
        super(MockedDisk, self).__init__()
        for i in "Name", "VolumeName", "SerialNumber",\
                 "VolumeSerialNumber", "Label":
            setattr(self, i, str(i))


class TestHelpers(BaseTestCase):
    def test_Win32_volume_mount(self):
        self.assertEquals(Win32_volume_mount(MockedDisk()),
                          "Name (Serial Number: SerialNumber) - Label")

    def test_win32_logicaldisk_mount(self):
        self.assertEquals(win32_logicaldisk_mount(MockedDisk()),
                          "Name (Serial Number: VolumeSerialNumber) - VolumeName")

    def test_win32_mapped_logicaldisk_mount(self):
        self.assertEquals(win32_mapped_logicaldisk_mount(MockedDisk()),
                          "Name (Serial Number: VolumeSerialNumber) - VolumeName")

    def test_guess_block_size(self):
        self.assertEquals(guess_block_size(None), 4096)
        self.assertEquals(guess_block_size(1000), 512)
