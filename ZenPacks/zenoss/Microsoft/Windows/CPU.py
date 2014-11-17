##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.ZenModel.CPU import CPU as BaseCPU


class CPU(BaseCPU):
    '''
    Model class for CPU.
    '''
    meta_type = portal_type = 'WindowsCPU'

    description = None
    cores = None
    threads = None
    cacheSpeedL2 = None
    cacheSizeL3 = None
    cacheSpeedL3 = None

    _properties = BaseCPU._properties + (
        {'id': 'description', 'label': 'Description', 'type': 'string', 'mode': 'w'},
        {'id': 'cores', 'label': 'Cores', 'type': 'int', 'mode': 'w'},
        {'id': 'threads', 'label': 'Threads', 'type': 'int', 'mode': 'w'},
        {'id': 'cacheSpeedL2', 'label': 'L2 Cache Speed', 'type': 'int', 'mode': 'w'},
        {'id': 'cacheSizeL3', 'label': 'L3 Cache Size', 'type': 'int', 'mode': 'w'},
        {'id': 'cacheSpeedL3', 'label': 'L3 Cache Speed', 'type': 'int', 'mode': 'w'},
        )

    def getRRDTemplateName(self):
        return 'CPU'

    def getIconPath(self):
        '''
        Return the path to an icon for this component.
        '''
        return '/++resource++mswindows/img/CPU.png'
