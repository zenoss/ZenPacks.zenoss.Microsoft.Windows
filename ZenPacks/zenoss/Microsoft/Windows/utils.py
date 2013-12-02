##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Basic utilities that don't cause any Zope stuff to be imported.
'''

import itertools


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


def get_processText(item):
    '''
    Return the OSProcess.processText given a Win32_Process item.
    '''
    if item.CommandLine:
        item.CommandLine = item.CommandLine.strip('"')

    return item.CommandLine or item.ExecutablePath or item.Name


def get_processNameAndArgs(item):
    '''
    Return (name, args) tuple given a Win32_Process item.
    '''
    name = item.ExecutablePath or item.Name
    if item.CommandLine:
        item.CommandLine = item.CommandLine.strip('"')
        args = item.CommandLine.replace(
            name, '', 1).strip()
    else:
        args = ''

    return (name, args)
