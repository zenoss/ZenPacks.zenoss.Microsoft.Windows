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


def lookup_architecture(value):
    return {
        0: 'x86',
        1: 'MIPS',
        2: 'Alpha',
        3: 'PowerPC',
        5: 'ARM',
        6: 'Itanium-based systems',
        9: 'x64',
        }.get(value, 'unknown')


def lookup_routetype(value):
    return {
        1: 'Other',
        2: 'Invalid',
        3: 'Direct',
        4: 'Indirect',
        }.get(value, 'unknown')


def lookup_protocol(value):
    return {
        1: 'Other',
        2: 'Local',
        3: 'Netmgmt',
        4: 'ICMP',
        5: 'egp',
        6: 'ggp',
        7: 'hello',
        8: 'rip',
        9: 'is-is',
        10: 'es-is',
        11: 'Ciscolgrp',
        12: 'bbnSpflgp',
        13: 'ospf',
        14: 'bgp',
        }.get(value, 'unknown')


def lookup_drivetype(value):
    return {
        0: 'Unknown',
        1: 'No Root Directory',
        2: 'Removable Disk',
        3: 'Local Disk',
        4: 'Network Drive',
        5: 'Compact Disc',
        6: 'RAM Disk',
        }.get(value, 'Unknown')


def lookup_zendrivetype(value):
    return {
        0: ['other'],
        2: ['removableDisk', 'floppyDisk'],
        3: ['fixedDisk'],
        4: ['networkDisk'],
        5: ['compactDisk'],
        6: ['ramDisk', 'virtualMemory', 'ram', 'flashMemory'],
        }.get(value, 'uknown')


def lookup_operstatus(value):
    if value == 'true':
        return 1
    else:
        return 2


def guessBlockSize(bytes):
    """Most of the MS operating systems don't seem to return a value
    for block size.  So, let's try to guess by how the size is rounded
    off.  That is, if the number is divisible by 1024, that's probably
    due to the block size.  Ya, it's a kludge."""
    for i in range(10, 17):
        if int(bytes) / float(1 << i) % 1:
            return 1 << (i - 1)
    return 4096                 # a total fiction


def parseDBUserNamePass(dbinstances='', dbinstancespassword=''):
    dblogins = {}
    if len(dbinstances) > 0 and len(dbinstancespassword) > 0:
        arrInstance = dbinstances.split(';')
        arrPassword = dbinstancespassword.split(';')
        i = 0
        for instance in arrInstance:
            dbuser, dbpass = arrPassword[i].split(':')
            i = i + 1
            dblogins[instance] = {'username': dbuser, 'password': dbpass}
    else:
        dblogins['MSSQLSERVER'] = {'username': 'sa', 'password': ''}

    return dblogins


def getSQLAssembly():

    ASSEMBLY_Connection = "add-type -AssemblyName 'Microsoft.SqlServer.ConnectionInfo"
    ASSEMBLY_Smo = "add-type -AssemblyName 'Microsoft.SqlServer.Smo"

    ASSEMBLY = "Culture=neutral, PublicKeyToken=89845dcd8080cc91'"
    ASSEMBLY_2005 = 'Version=9.0.242.0'
    ASSEMBLY_2008 = 'Version=10.0.0.0'
    ASSEMBLY_2012 = 'Version=11.0.0.0'

    MSSQL2005_CONNECTION_INFO = '{0}, {1}, {2}'.format(
        ASSEMBLY_Connection,
        ASSEMBLY_2005,
        ASSEMBLY)

    MSSQL2008_CONNECTION_INFO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Connection,
        ASSEMBLY_2008,
        ASSEMBLY)

    MSSQL2012_CONNECTION_INFO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Connection,
        ASSEMBLY_2012,
        ASSEMBLY)

    MSSQL2005_SMO = '{0}, {1}, {2}'.format(
        ASSEMBLY_Smo,
        ASSEMBLY_2005,
        ASSEMBLY)

    MSSQL2008_SMO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Smo,
        ASSEMBLY_2008,
        ASSEMBLY)

    MSSQL2012_SMO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Smo,
        ASSEMBLY_2012,
        ASSEMBLY)

    sqlConnection = []
    sqlConnection.append("try{")
    sqlConnection.append(MSSQL2012_CONNECTION_INFO)
    sqlConnection.append("}catch{")
    sqlConnection.append("try{")
    sqlConnection.append(MSSQL2008_CONNECTION_INFO)
    sqlConnection.append("}catch{")
    sqlConnection.append(MSSQL2005_CONNECTION_INFO)
    sqlConnection.append("}};")

    sqlConnection.append("try{")
    sqlConnection.append(MSSQL2012_SMO)
    sqlConnection.append("}catch{")
    sqlConnection.append("try{")
    sqlConnection.append(MSSQL2008_SMO)
    sqlConnection.append("}catch{")
    sqlConnection.append(MSSQL2005_SMO)
    sqlConnection.append("}};")

    return sqlConnection
