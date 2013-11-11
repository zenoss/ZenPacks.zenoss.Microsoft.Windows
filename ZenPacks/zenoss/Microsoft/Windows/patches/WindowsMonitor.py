##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Patches to be applied only if ZenPacks.zenoss.WindowsMonitor is
installed.
'''

from Products.ZenUtils.Utils import monkeypatch

from ZenPacks.zenoss.Microsoft.Windows import SHARED_ZPROPERTIES


@monkeypatch('ZenPacks.zenoss.WindowsMonitor.ZenPack')
def remove(self, app, leaveObjects=False):
    '''
    Override WindowsMonitor ZenPack remove.

    This is done to allow sharing of zWinUser and zWinPassword
    configuration properties.
    '''
    # Disassociate WindowsMonitor from shared zProperties.
    self.packZProperties = [
        t for t in self.packZProperties if t[0] not in SHARED_ZPROPERTIES]

    # original is injected by @monkeypatch decorator.
    original(self, app, leaveObjects=leaveObjects)
