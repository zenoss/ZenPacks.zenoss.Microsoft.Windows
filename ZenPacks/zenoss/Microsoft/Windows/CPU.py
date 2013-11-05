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

    core = None
    thread = None

    _properties = BaseCPU._properties + (
        {'id': 'core', 'type': 'string', 'mode': 'w'},
        {'id': 'thread', 'type': 'string', 'mode': 'w'},
        )
