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

    _properties = BaseFileSystem._properties + (
        {'id': 'mediatype', 'type': 'string', 'mode': 'w'},
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
