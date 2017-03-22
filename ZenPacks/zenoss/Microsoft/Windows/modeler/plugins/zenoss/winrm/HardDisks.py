##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Windows Hard Disks

Models hard disks by querying Win32_Disk via WMI.
'''
from Products.DataCollector.plugins.DataMaps import MultiArgs
from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import save


class HardDisks(WinRMPlugin):
    compname = 'hw'
    relname = 'harddisks'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.HardDisk'

    associators = {
        'diskdrives': {
            'seed_class': 'Win32_DiskDrive',
            'associations': [{'return_class': 'Win32_DiskDriveToDiskPartition',
                              'search_class': 'Win32_DiskDrive',
                              'search_property': 'DeviceID',
                              'where_type': 'AssocClass'},
                             {'return_class': 'Win32_LogicalDiskToPartition',
                              'search_class': 'Win32_DiskPartition',
                              'search_property': 'DeviceID',
                              'where_type': 'AssocClass'
                              }]
        }
    }

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler {} processing data for device {}".format(
                self.name(), device.id))

        rm = self.relMap()
        try:
            diskdrives = results.get('diskdrives').get('Win32_DiskDrive')
        except Exception:
            return rm
        if not diskdrives:
            return rm
        partitions = results.get('diskdrives').get('Win32_DiskDriveToDiskPartition')
        volumes = results.get('diskdrives').get('Win32_LogicalDiskToPartition')
        for drive in diskdrives:
            utilization = 0
            fs_ids = []
            instance_name = '{}'.format(drive.Index)
            try:
                for partition in partitions[drive.DeviceID]:
                    utilization += int(partition.Size)
                    for volume in volumes[partition.DeviceID]:
                        fs_ids.append(self.prepId(volume.DeviceID))
                        instance_name += ' {}'.format(volume.DeviceID)
            except Exception:
                log.debug("No partitions for drive {} on {}.".format(instance_name, device.id))
            freespace = int(drive.Size) - utilization
            if freespace < 0:
                freespace = 0
            try:
                num_partitions = int(drive.Partitions)
            except TypeError:
                num_partitions = 0
            try:
                size = int(drive.Size)
            except TypeError:
                size = 0
            serialNumber = drive.SerialNumber.strip() if hasattr(drive, 'SerialNumber') else ''
            product_key = MultiArgs(drive.Model, drive.Manufacturer)
            capabilities = drive.CapabilityDescriptions if hasattr(drive, 'CapabilityDescriptions') else ''
            rm.append(self.objectMap({
                'id': self.prepId(drive.PNPDeviceID),
                'title': drive.Caption,
                'size': size,
                'partitions': num_partitions,
                'capabilities': capabilities,
                'serialNumber': serialNumber,
                'freespace': freespace,
                'disk_ids': make_disk_ids(drive),
                'fs_ids': fs_ids,
                'instance_name': instance_name,
                'setProductKey': product_key
            }))
        return rm


def reorder_serial(input_serial):
    """
    Take a serial number and reorder it into the orginal.

    This will exclude the first 2 digits from the original format
    since those are lost on the Windows side.
    String must have even number of characters.
    """
    size = len(input_serial)
    if size % 2 != 0:
        return

    # Remove the first 2 characters since not unique
    input_serial = input_serial[2:]
    new_serial = ''
    for i in range(size, 0, -2):
        new_serial += input_serial[i - 2:i]

    return new_serial


def make_disk_ids(disk_drive):
    """From a Win32_DiskDrive object, create the disk_ids list."""
    disk_ids = []
    disk_ids.append(disk_drive.DeviceID)

    # If no PNPDeviceID, its not a physical disk, so return None
    pnpDevice = disk_drive.PNPDeviceID.strip()
    if not pnpDevice:
        return

    disk_ids.append(pnpDevice)

    # Append SerialNumber
    serial = disk_drive.SerialNumber.strip() if hasattr(disk_drive, 'SerialNumber') else None
    if not serial:
        return disk_ids

    disk_ids.append(serial)

    # Append the reordered serial to match CiscoUCS, minus first 2 characters
    size = len(serial)
    if size == 32:
        disk_ids.append(reorder_serial(serial))

    return disk_ids
