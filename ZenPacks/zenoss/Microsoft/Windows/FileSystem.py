##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from . import schema
from .utils import get_properties

class FileSystem(schema.FileSystem):
    '''
    Model class for FileSystem.
    '''

    _properties = get_properties(schema.FileSystem)

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

    @property
    def total_bytes(self):
        """
        Return the total bytes of a filesytem for analytics
        """
        return self.blockSize * self.totalBlocks
