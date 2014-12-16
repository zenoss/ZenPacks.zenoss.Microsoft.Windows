##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenModel.FileSystem import FileSystem as BaseFileSystem


class FileSystem(BaseFileSystem):
    mediatype = None
    total_bytes = 0

    _properties = BaseFileSystem._properties + (
        {'id': 'mediatype', 'label': 'Media Type',
            'type': 'string', 'mode': 'w'},
        {'id':'total_bytes', '': 'Total Bytes',
            'type':'long', 'mode':''},
        )

    def monitored(self):
        '''
        Return the monitored status of this component. Default is False.

        Overridden from BaseFileSystem to avoid monitoring file systems
        that aren't a fixed disk or have zero capacity.
        '''
        if not self.totalBlocks:
            return False

        if self.mediatype not in ('Format is unknown', 'Fixed hard disk media'):
            return False

        return self.monitor and True

    def getIconPath(self):
        '''
        Return the path to an icon for this component.
        '''
        return '/++resource++mswindows/img/FileSystem.png'

    @property
    def total_bytes(self):
        """
        Return the total bytes of a filesytem for analytics
        """
        return self.blockSize * self.totalBlocks
