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

from ZenPacks.zenoss.Microsoft.Windows.tests.mock import Mock
from Products.ZenTestCase.BaseTestCase import BaseTestCase
from ZenPacks.zenoss.Microsoft.Windows.tests.utils import StringAttributeObject
from ZenPacks.zenoss.Microsoft.Windows.modeler.plugins.zenoss.winrm.HardDisks import HardDisks
from txwinrm.enumerate import ItemsAccumulator

Win32_DiskDrive = {
    "Availability": None,
    "BytesPerSector": '512',
    "Capabilities": ['3', '4'],
    "CapabilityDescriptions": ['Random Access', 'Supports Writing'],
    "Caption": 'VMware Virtual disk SCSI Disk Device',
    "CompressionMethod": None,
    "ConfigManagerErrorCode": '0',
    "ConfigManagerUserConfig": 'false',
    "CreationClassName": 'Win32_DiskDrive',
    "DefaultBlockSize": None,
    "Description": 'Disk drive',
    "DeviceID": '\\\\.\\PHYSICALDRIVE0',
    "ErrorCleared": None,
    "ErrorDescription": None,
    "ErrorMethodology": None,
    "FirmwareRevision": '1.0 ',
    "Index": '0',
    "InstallDate": None,
    "InterfaceType": 'SCSI',
    "LastErrorCode": None,
    "Manufacturer": '(Standard disk drives)',
    "MaxBlockSize": None,
    "MaxMediaSize": None,
    "MediaLoaded": 'true',
    "MediaType": 'Fixed hard disk media',
    "MinBlockSize": None,
    "Model": 'VMware Virtual disk SCSI Disk Device',
    "Name": '\\\\.\\PHYSICALDRIVE0',
    "NeedsCleaning": None,
    "NumberOfMediaSupported": None,
    "PNPDeviceID": 'SCSI\\DISK&VEN_VMWARE&PROD_VIRTUAL_DISK\\4&3B5019BE&0&000000',
    "Partitions": '2',
    "PowerManagementSupported": None,
    "SCSIBus": '0',
    "SCSILogicalUnit": '0',
    "SCSIPort": '2',
    "SCSITargetId": '0',
    "SectorsPerTrack": '63',
    "SerialNumber": None,
    "Signature": '4136689105',
    "Size": '42944186880',
    "Status": 'OK',
    "StatusInfo": None,
    "SystemCreationClassName": 'Win32_ComputerSystem',
    "SystemName": 'CA',
    "TotalCylinders": '5221',
    "TotalHeads": '255',
    "TotalSectors": '83875365',
    "TotalTracks": '1331355',
    "TracksPerCylinder": '255'}

Win32_LogicalDiskToPartition = {"Disk #0, Partition #0": {}, "Disk #0, Partition #1": {
    "Access": '0',
    "Availability": None,
    "BlockSize": None,
    "Caption": 'C:',
    "Compressed": 'false',
    "ConfigManagerErrorCode": None,
    "ConfigManagerUserConfig": None,
    "CreationClassName": 'Win32_LogicalDisk',
    "Description": 'Local Fixed Disk',
    "DeviceID": 'C:',
    "DriveType": '3',
    "ErrorCleared": None,
    "ErrorDescription": None,
    "ErrorMethodology": None,
    "FileSystem": 'NTFS',
    "FreeSpace": '5914783744',
    "InstallDate": None,
    "LastErrorCode": None,
    "MaximumComponentLength": '255',
    "MediaType": '12',
    "Name": 'C:',
    "NumberOfBlocks": None,
    "PNPDeviceID": None,
    "PowerManagementSupported": None,
    "ProviderName": None,
    "Purpose": None,
    "QuotasDisabled": 'true',
    "QuotasIncomplete": 'false',
    "QuotasRebuilding": 'false',
    "Size": '42841665536',
    "Status": None,
    "StatusInfo": None,
    "SupportsDiskQuotas": 'true',
    "SupportsFileBasedCompression": 'true',
    "SystemCreationClassName": 'Win32_ComputerSystem',
    "SystemName": 'CA',
    "VolumeDirty": 'false',
    "VolumeName": '',
    "VolumeSerialNumber": 'AC8091FA'}}

Win32_DiskDriveToDiskPartition = {"\\\\.\\PHYSICALDRIVE0": [{
    "Access": None,
    "Availability": None,
    "BlockSize": '512',
    "BootPartition": 'true',
    "Bootable": 'true',
    "Caption": 'Disk #0, Partition #0',
    "ConfigManagerErrorCode": None,
    "ConfigManagerUserConfig": None,
    "CreationClassName": 'Win32_DiskPartition',
    "Description": 'Installable File System',
    "DeviceID": 'Disk #0, Partition #0',
    "DiskIndex": '0',
    "ErrorCleared": None,
    "ErrorDescription": None,
    "ErrorMethodology": None,
    "HiddenSectors": None,
    "Index": '0',
    "InstallDate": None,
    "LastErrorCode": None,
    "Name": 'Disk #0, Partition #0',
    "NumberOfBlocks": '204800',
    "PNPDeviceID": None,
    "PowerManagementSupported": None,
    "PrimaryPartition": 'true',
    "Purpose": None,
    "RewritePartition": None,
    "Size": '104857600',
    "StartingOffset": '1048576',
    "Status": None,
    "StatusInfo": None,
    "SystemCreationClassName": 'Win32_ComputerSystem',
    "SystemName": 'CA',
    "Type": 'Installable File System'
}, {
    "Access": None,
    "Availability": None,
    "BlockSize": '512',
    "BootPartition": 'false',
    "Bootable": 'false',
    "Caption": 'Disk #0, Partition #1',
    "ConfigManagerErrorCode": None,
    "ConfigManagerUserConfig": None,
    "CreationClassName": 'Win32_DiskPartition',
    "Description": 'Installable File System',
    "DeviceID": 'Disk #0, Partition #1',
    "DiskIndex": '0',
    "ErrorCleared": None,
    "ErrorDescription": None,
    "ErrorMethodology": None,
    "HiddenSectors": None,
    "Index": '1',
    "InstallDate": None,
    "LastErrorCode": None,
    "Name": 'Disk #0, Partition #1',
    "NumberOfBlocks": '83675136',
    "PNPDeviceID": None,
    "PowerManagementSupported": None,
    "PrimaryPartition": 'true',
    "Purpose": None,
    "RewritePartition": None,
    "Size": '42841669632',
    "StartingOffset": '105906176',
    "Status": None,
    "StatusInfo": None,
    "SystemCreationClassName": 'Win32_ComputerSystem',
    "SystemName": 'CA',
    "Type": 'Installable File System'}]}


def get_items(accumulator, disk_dict):
    for k, v in disk_dict.iteritems():
        accumulator.add_property(k, v)


def create_results():
    accumulator = ItemsAccumulator()
    accumulator.new_item()
    get_items(accumulator, Win32_DiskDrive)
    results = {'diskdrives': {
        'Win32_DiskDrive': accumulator.items,
        'Win32_LogicalDiskToPartition': {},
        'Win32_DiskDriveToDiskPartition': {}}}
    del accumulator
    for k, v in Win32_LogicalDiskToPartition.iteritems():
        accumulator = ItemsAccumulator()
        accumulator.new_item()
        get_items(accumulator, v)
        results['diskdrives']['Win32_LogicalDiskToPartition'][k] = accumulator.items
    del accumulator
    for k, v in Win32_DiskDriveToDiskPartition.iteritems():
        accumulator = ItemsAccumulator()
        for props in v:
            accumulator.new_item()
            get_items(accumulator, props)
        results['diskdrives']['Win32_DiskDriveToDiskPartition'][k] = accumulator.items
    return results


class TestHardDisks(BaseTestCase):
    def setUp(self):
        self.plugin = HardDisks()
        self.results = create_results()

    def testZPS1279(self):
        data = self.plugin.process(StringAttributeObject(), self.results, Mock())
        self.assertEquals(len(data.maps), 1)
        self.assertEquals(data.maps[0].serialNumber, '')
        self.assertEquals(data.maps[0].id, 'SCSI_DISK_VEN_VMWARE_PROD_VIRTUAL_DISK_4_3B5019BE_0_000000')
        self.assertEquals(data.maps[0].partitions, 2)
        self.assertEquals(data.maps[0].disk_ids, ['\\\\.\\PHYSICALDRIVE0',
                                                  'SCSI\\DISK&VEN_VMWARE&PROD_VIRTUAL_DISK\\4&3B5019BE&0&000000'])


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestHardDisks))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
