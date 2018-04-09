##############################################################################
#
# Copyright (C) Zenoss, Inc. 2017, 2018, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from zope.component import adapts
from zope.interface import implements

from Products.Zuul.catalog.interfaces import IIndexableWrapper
from ZenPacks.zenoss.ZenPackLib.lib.wrapper.ComponentIndexableWrapper import \
    ComponentIndexableWrapper

from ZenPacks.zenoss.Microsoft.Windows.utils import keyword_search

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
        """Return a generator of the storage disks/virtual drives based on disk_ids."""
        keywords = set()
        if self.disk_ids:
            for disk_id in self.disk_ids:
                # Add disk_id to keywords to save compatibility with UCS storage
                keywords.add(disk_id)

                keywords.add(
                    'has-target-wwn:{}'.format(disk_id)
                )

            for obj in keyword_search(self.getDmdRoot('Devices'), keywords):
                yield obj


class HardDiskIndexableWrapper(ComponentIndexableWrapper):
    implements(IIndexableWrapper)
    adapts(HardDisk)

    def searchKeywordsForChildren(self):
        """Return tuple of search keywords for HardDisk objects."""
        keywords = set()
        disk_ids = self._context.disk_ids

        if disk_ids:
            for disk_id in disk_ids:
                # add uses-target-wwn keyword to make it possible to find
                # this HardDisk from an appropriate storage provider
                keywords.add(
                    'uses-target-wwn:{}'.format(disk_id)
                )

        return (super(HardDiskIndexableWrapper, self).searchKeywordsForChildren() +
                tuple(keywords))
