##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Globals import InitializeClass

from Products.ZenModel.HWComponent import HWComponent
from Products.ZenRelations.RelSchema import ToOne, ToManyCont


class WinProc(HWComponent):
    '''
    Model class for Windows Processor.
    '''
    meta_type = portal_type = 'WinRMProc'

    caption = None
    numbercore = None
    status = None
    architecture = None
    clockspeed = None
    voltage = None

    _properties = HWComponent._properties + (
        {'id': 'caption', 'type': 'string'},
        {'id': 'numbercore', 'type': 'string'},
        {'id': 'status', 'type': 'string'},
        {'id': 'architecture', 'type': 'string'},
        {'id': 'clockspeed', 'type': 'string'},
        )

    _relations = HWComponent._relations + (
        ("hw", ToOne(ToManyCont,
         "ZenPacks.zenoss.Microsoft.Windows.Hardware",
         "winrmproc")),
    )

InitializeClass(WinProc)
