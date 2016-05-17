##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Common datasource utilities.
'''
from Products.ZenEvents import ZenEventClasses


def checkExpiredPassword(config, events, error):
    if 'Password expired' in error:
        events.append({
            'eventClass': '/Status/Winrm/Ping',
            'severity': ZenEventClasses.Critical,
            'summary': error,
            'ipAddress': config.manageIp,
            'device': config.id})
