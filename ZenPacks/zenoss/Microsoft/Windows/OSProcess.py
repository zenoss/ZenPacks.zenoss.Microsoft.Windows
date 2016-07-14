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

from Products.ZenModel.OSProcess import OSProcess as BaseOSProcess


class OSProcess(schema.OSProcess):
    '''
    Model class for OSProcess.

    Extended here to support alternate monitoring template binding.
    Depending on the version of Windows there are different per-process
    counters available.
    '''

    _properties = get_properties(schema.OSProcess)

    def getClassObject(self):
        return BaseOSProcess.getClassObject(self)

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
