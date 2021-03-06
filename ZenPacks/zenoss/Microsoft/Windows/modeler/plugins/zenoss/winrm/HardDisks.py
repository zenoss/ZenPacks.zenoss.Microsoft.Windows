##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, 2018, all rights reserved.
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

    powershell_commands = {
        'signature_uniqueid': (
          "Get-Disk | ForEach-Object {$_.Signature, '=', $_.UniqueId, '|'};"
        )
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

        uniqueids_dict = {}
        signature_uniqueid = results.get('signature_uniqueid')
        if signature_uniqueid:
            signature_uniqueid = ''.join(signature_uniqueid.stdout).split('|')
            for ids in signature_uniqueid:
                try:
                    key, value = ids.split('=')
                    uniqueids_dict[key] = value
                except (KeyError, ValueError):
                    pass

        for drive in diskdrives:
            utilization = 0
            fs_ids = []
            instance_name = '{}'.format(drive.Index)
            try:
                for partition in partitions[drive.DeviceID]:
                    try:
                        partsize = int(partition.Size)
                    except (TypeError, ValueError):
                        partsize = 0
                    utilization += partsize
                    for volume in volumes[partition.DeviceID]:
                        fs_ids.append(self.prepId(volume.DeviceID))
                        instance_name += ' {}'.format(volume.DeviceID)
            except Exception:
                log.debug("No partitions for drive {} on {}.".format(instance_name, device.id))
            try:
                size = int(drive.Size)
            except (TypeError, ValueError):
                size = 0
            freespace = size - utilization
            if freespace < 0:
                freespace = 0
            try:
                num_partitions = int(drive.Partitions)
            except TypeError:
                num_partitions = 0

            # drive.SerialNumber could be None.  let's make it ''
            serialNumber = ''
            if hasattr(drive, 'SerialNumber'):
                if drive.SerialNumber is None:
                    drive.SerialNumber = ''
                serialNumber = drive.SerialNumber.strip()
            if hasattr(drive, 'Signature'):
                drive.uniqueId = uniqueids_dict.get(drive.Signature)

            product_key = MultiArgs(drive.Model, drive.Manufacturer)
            capabilities = ''
            if hasattr(drive, 'CapabilityDescriptions') and drive.CapabilityDescriptions:
                capabilities = drive.CapabilityDescriptions
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

    # Append UniqueId of hard disk
    unique_id = getattr(disk_drive, 'uniqueId', None)
    if unique_id:
        disk_ids.append(unique_id)

    # If no PNPDeviceID, its not a physical disk, so return None
    pnpDevice = disk_drive.PNPDeviceID.strip()
    if not pnpDevice:
        return

    disk_ids.append(pnpDevice)

    # Append SerialNumber
    serial = None
    if hasattr(disk_drive, 'SerialNumber'):
        serial = disk_drive.SerialNumber.strip()
    if not serial:
        return disk_ids

    disk_ids.append(serial)

    # Append the reordered serial to match CiscoUCS, minus first 2 characters
    size = len(serial)
    if size == 32:
        disk_ids.append(reorder_serial(serial))

    return disk_ids
