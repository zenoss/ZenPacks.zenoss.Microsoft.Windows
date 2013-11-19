##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenModel.OSProcess import OSProcess as OSProcessBase


class OSProcess(OSProcessBase):
    '''
    Model class for OSProcess.

    Extended here to support alternate monitoring template binding.
    Depending on the version of Windows there are different per-process
    counters available.
    '''

    supports_WorkingSetPrivate = None

    _properties = OSProcessBase._properties + (
        {'id': 'supports_WorkingSetPrivate', 'type': 'boolean', 'mode': 'w'},
        )

    def getRRDTemplateName(self):
        '''
        Return monitoring template name appropriate for this component.

        Overridden to support different per-process monitoring
        requirements for Windows 2003 servers.
        '''
        default = super(OSProcess, self).getRRDTemplateName()

        if self.supports_WorkingSetPrivate is False:
            return '-'.join((default, '2003'))

        return default
