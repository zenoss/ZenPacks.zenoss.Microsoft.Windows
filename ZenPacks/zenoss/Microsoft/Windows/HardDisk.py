##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from Products.Zuul.interfaces import ICatalogTool
from Products.AdvancedQuery import Eq, Or

from . import schema


class HardDisk(schema.HardDisk):
    """Model class for HardDisk."""

    def utilization(self):
        if self.size == 0:
            return 'Unknown'

        util = int(float(self.size - self.freespace) / self.size * 100)

        return '{}%'.format(util)

    def filesystems(self):
        file_systems = []
        for fs in self.fs_ids:
            try:
                filesystem = self.device().os.filesystems._getOb(fs)
            except Exception:
                pass
            else:
                file_systems.append(filesystem)
        return file_systems

    def monitored(self):
        if self.size == 0 and self.partitions == 0:
            return False
        return self.monitor and True

    def storage_disk_lun(self):
        # return the UCS storage disk/virtual drive
        # if disk_ids contains the IDs of disk/virtual drive
        if self.disk_ids:
            results = ICatalogTool(self.getDmdRoot('Devices')).search(
                query=Or(*[Eq('searchKeywords', id)
                           for id in self.disk_ids]))

            for brain in results:
                try:
                    yield brain.getObject()
                except Exception:
                    continue
