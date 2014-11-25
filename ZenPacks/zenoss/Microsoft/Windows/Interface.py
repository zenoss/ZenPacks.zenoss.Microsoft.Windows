##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


from Products.ZenModel.IpInterface import IpInterface
from Products.ZenRelations.RelSchema import ToMany, ToOne


class Interface(IpInterface):
    portal_type = meta_type = 'WindowsInterface'

    _relations = IpInterface._relations + (
        ('teaminterface', ToOne(ToMany,
            'ZenPacks.zenoss.Microsoft.Windows.TeamInterface',
            'teaminterfaces')),
        )

    def __init__(self, *args, **kwargs):
        super(IpInterface, self).__init__(*args, **kwargs)
        # Default to False for monitoring
        self.monitor = False

    def monitored(self):
        '''
        Return the monitored status of this component.

        Overridden from IpInterface to prevent monitoring
        administratively down interfaces.
        '''
        return self.monitor

    def getIconPath(self):
        '''
        Return the path to an icon for this component.
        '''
        return '/++resource++mswindows/img/Interface.png'
