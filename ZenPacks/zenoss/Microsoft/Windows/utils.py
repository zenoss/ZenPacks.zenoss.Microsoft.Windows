##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################


def addLocalLibPath():
    """
    Helper to add the ZenPack's lib directory to PYTHONPATH.
    """
    import os
    import site

    site.addsitedir(os.path.join(os.path.dirname(__file__), 'lib'))


def lookup_adminpasswordstatus(value):
    return {
        1: 'Disabled',
        2: 'Enabled',
        3: 'Not Implemented',
        4: 'Unknown',
       }.get(value, 'unknown')


def lookup_chassisbootupstate(value):
    return {
        1: 'Other',
        2: 'Unknown',
        3: 'Safes',
        4: 'Warning',
        5: 'Critical',
        6: 'Nonrecoverable',
        }.get(value, 'unknown')


def lookup_domainrole(value):
    return {
        1: 'Standalone Workstation',
        2: 'Member Workstation',
        3: 'Standalone Server',
        4: 'Member Server',
        5: 'Backup Domain Controller',
        6: 'Primary Domain Controller',
        }.get(value, 'unknown')


def lookup_powerstate(value):
    return {
        1: 'Full Power',
        2: 'Power Save - Low Power Mode',
        3: 'Power Save - Standby',
        4: 'Power Save - Unknown',
        5: 'Power Cycle',
        6: 'Power Off',
        7: 'Power Save - Warning',
        }.get(value, 'unknown')
