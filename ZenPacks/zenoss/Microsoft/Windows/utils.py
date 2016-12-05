##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Basic utilities that don't cause any Zope stuff to be imported.
'''

import json
from Products.ZenEvents import ZenEventClasses

def get_properties(klass):
    '''
        avoid duplicates when adding properties 
        to ZPL schema-based class from a base class
    '''
    seen = set()
    seen_add = seen.add
    props = tuple([x for x in klass._properties if not (x.get('id') in seen or seen_add(x.get('id')))])
    return props

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


def parseDBUserNamePass(dbinstances='', username='', password=''):
    """
    Try to get username(s)/password(s) from configuration,
    if not - uses WinRM credentials.
    """
    dblogins = {}
    try:
        dbinstance = json.loads(prepare_zDBInstances(dbinstances))
        users = [el.get('user') for el in filter(None, dbinstance)]
        # a) MSSQL auth
        if ''.join(users):
            for el in filter(None, dbinstance):
                dblogins[el.get('instance')] = dict(
                    username=el.get('user') if el.get('user') else username,
                    password=el.get('passwd') if el.get('passwd') else password,
                    login_as_user=False if el.get('user') else True
                )
        # b) Windows auth
        else:
            for el in filter(None, dbinstance):
                dblogins[el.get('instance')] = dict(
                    username=username,
                    password=password,
                    login_as_user=True
                )

            # Retain the default behaviour, before zProps change.
            if not dbinstance:
                dblogins['MSSQLSERVER'] = {
                    'username': username, # 'sa',
                    'password': password,
                    'login_as_user':True
                }
    except (ValueError, TypeError, IndexError):
        pass

    return dblogins


def filter_sql_stdout(val):
    """
    Filters SQL stdout from service messages
    """
    # SQL 2005 returns in stdout when Win auth
    return filter(lambda x: x!="LogonUser succedded", val)


def getSQLAssembly(version=None):
    """Return only the powershell assembly version needed for the instance.
    These statements are prepended to any sql server connections.
    SQL server 2012 and 2014 can use the same version.
    If no version is given then return all and hope the first one that
    loads is correct.
    Multiple versions of sql server can co-exist on the same machine.

    example using sql server 11 or 12
    try {
        add-type -AssemblyName 'Microsoft.SqlServer.ConnectionInfo, Version=11.0.0.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91' -EA Stop
    }
    catch {
        write-host 'assembly load error'
    }
    try {
        add-type -AssemblyName 'Microsoft.SqlServer.Smo, Version=11.0.0.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91' -EA Stop
    }
    catch {
        write-host 'assembly load error'
    }

    TODO:  Test with 2016 server
    """
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

    MSSQL_CONNECTION_INFO = {9: MSSQL2005_CONNECTION_INFO,
                             10: MSSQL2008_CONNECTION_INFO,
                             11: MSSQL2012_CONNECTION_INFO,
                             12: MSSQL2012_CONNECTION_INFO}

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

    MSSQL_SMO = {9: MSSQL2005_SMO,
                 10: MSSQL2008_SMO,
                 11: MSSQL2012_SMO,
                 12: MSSQL2012_SMO}

    ASSEMBLY_LOAD_ERROR = "write-host 'assembly load error'"

    sqlConnection = []
    if version not in [9, 10, 11, 12]:
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2012_CONNECTION_INFO)
        sqlConnection.append("}catch{")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2008_CONNECTION_INFO)
        sqlConnection.append("}catch{")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2005_CONNECTION_INFO)
        sqlConnection.append("}catch{")
        sqlConnection.append(ASSEMBLY_LOAD_ERROR)
        sqlConnection.append("}}}")

        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2012_SMO)
        sqlConnection.append("}catch{")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2008_SMO)
        sqlConnection.append("}catch{")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2005_SMO)
        sqlConnection.append("}catch{")
        sqlConnection.append(ASSEMBLY_LOAD_ERROR)
        sqlConnection.append("}}}")
    else:
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL_CONNECTION_INFO.get(version))
        sqlConnection.append("}catch{")
        sqlConnection.append(ASSEMBLY_LOAD_ERROR)
        sqlConnection.append("}")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL_SMO.get(version))
        sqlConnection.append("}catch{")
        sqlConnection.append(ASSEMBLY_LOAD_ERROR)
        sqlConnection.append("}")

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


def check_for_network_error(result, config):
    '''
    Checks value for timeout/no route to host tracebacks
    '''
    str_result = str(result)
    if 'No route to host' in str_result:
        return 'No route to host', '/Status'

    if 'timeout' in str_result:
        return 'Timeout while connecting to host', '/Status'

    if 'refused' in str_result:
        return 'Connection was refused by other side', '/Status'

    if 'Unauthorized' in str_result:
        return 'Unauthorized, check username and password', '/Status'

    msg = 'Failed collection {0} on {1}'.format(
        result.value.message, config
    )

    return msg, '/Unknown'


def prepare_zDBInstances(inst):
    '''
    Workaround for ZEN-11424
    '''
    dbinstance = inst
    if isinstance(inst, list):
        if inst[0].get('instance') and isinstance(inst[0].get('instance'), list):
            dbinstance = inst[0].get('instance')
            # checks if the pre_parced is list
            # check if the first element is dict
            if isinstance(dbinstance[0], dict):
                # Convert dict to string
                prep_inst = str(dbinstance[0])
                prep_inst = prep_inst.replace('\'', '"')
                dbinstance = '[' + prep_inst + ']'
        else:
            dbinstance = str(dbinstance).replace('\'', '"')
    return dbinstance


def sizeof_fmt(byte=0):
    try:
        byte = int(byte)
    except ValueError:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB']:
        if abs(byte) < 1024.0:
            return "%3.2f%s" % (byte, unit)
        byte /= 1024.0


def pipejoin(items):
    return " + '|' + ".join(items.split())


def cluster_state_string(state):
    return {0: 'Online',
            1: 'Up',
            2: 'Offline',
            3: 'PartialOnline',
            4: 'Failed'}.get(state, 'Unknown')


def cluster_state_value(state):
    return {'Online': 0,
            'Up': 1,
            'Offline': 2,
            'PartialOnline': 3,
            'Failed': 4}.get(state, 5)


def save(f):
    '''
    This is a decorator that will save arguments sent to a function.
    It will write to the /tmp directory using the class name, method name
    and write time as the file name.  It depends upon the 'ZP_DUMP' env
    variable existing to dump the pickle.  It then passes the args to the original
    function.  Be sure to unset ZP_DUMP or you'll see a lot of pickles

    We'll skip over device_proxy and config because they contain password in clear text

    usage:
    class foo(object):
        @save
        def bar(self, x, y):
            print 'x: {}, y: {}'.format(x, y)

    foo().bar(1, 2)

    $ export ZP_DUMP = 1; python foo.py; unset ZP_DUMP
    '''
    def dumper(self, *args, **kwargs):
        import os
        if os.environ.get('ZP_DUMP', None):
            import pickle
            import time
            import logging
            filetime = time.strftime('%H%M%S', time.localtime())
            fname = '_'.join((self.__class__.__name__, f.func_name, filetime))
            with open(os.path.join('/tmp', fname + '.pickle'), 'w') as pkl_file:
                arguments = []
                for count, thing in enumerate(args):
                    if (isinstance(thing, logging.Logger) or
                            isinstance(thing, file) or
                            hasattr(thing, 'windows_password') or
                            hasattr(thing, 'datasources')):
                                continue
                    arguments.append(thing)
                for name, thing in kwargs.items():
                    if (isinstance(thing, logging.Logger) or
                            isinstance(thing, file) or
                            hasattr(thing, 'windows_password') or
                            hasattr(thing, 'datasources')):
                                continue
                    arguments.append('{}={}'.format(name, thing))
                try:
                    pickle.dump(arguments, pkl_file)
                except TypeError:
                    pass
                pkl_file.close()
        return f(self, *args, **kwargs)
    return dumper

'''
Common datasource utilities.
'''

def errorMsgCheck(config, events, error):
    """Check error message and generate appropriate event."""
    if 'Password expired' in error:
        events.append({
            'eventClassKey': 'MW|PasswordExpired',
            'severity': ZenEventClasses.Critical,
            'summary': error,
            'ipAddress': config.manageIp,
            'device': config.id})
    elif 'Check username and password' in error:
        events.append({
            'eventClassKey': 'MW|WrongCredentials',
            'severity': ZenEventClasses.Critical,
            'summary': error,
            'ipAddress': config.manageIp,
            'device': config.id})


def generateClearAuthEvents(config, events):
    """Generate clear authentication events."""
    events.append({
        'eventClass': '/Status/Winrm/Auth/PasswordExpired',
        'eventClassKey': 'MW|PasswordExpired',
        'severity': ZenEventClasses.Clear,
        'summary': 'Password is not expired',
        'device': config.id})
    events.append({
        'eventClass': '/Status/Winrm/Auth/WrongCredentials',
        'eventClassKey': 'MW|WrongCredentials',
        'severity': ZenEventClasses.Clear,
        'summary': 'Credentials are OK',
        'device': config.id})
