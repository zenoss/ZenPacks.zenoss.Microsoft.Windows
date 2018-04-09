##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2018, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Basic utilities that doesn't cause any Zope stuff to be imported.
"""

import json
import base64
from Products.AdvancedQuery import In
from Products.Zuul.interfaces import ICatalogTool

APP_POOL_STATUSES = {
    1: 'Uninitialized',
    2: 'Initialized',
    3: 'Running',
    4: 'Disabling',
    5: 'Disabled',
    6: 'Shutdown Pending',
    7: 'Delete Pending'
}

DB_STATUSES = {
    1: 'AutoClosed',
    2: 'EmergencyMode',
    4: 'Inaccessible',
    8: 'Normal',
    16: 'Offline',
    32: 'Recovering',
    64: 'RecoveryPending',
    128: 'Restoring',
    256: 'Shutdown',
    512: 'Standby',
    1024: 'Suspect'
}


def addLocalLibPath():
    """
    Helper to add the ZenPack's lib directory to PYTHONPATH.
    """
    import os
    import site

    site.addsitedir(os.path.join(os.path.dirname(__file__), 'lib'))


def lookup_databasesummary(value):
    return {
        'AutoClosed': 'The database has been automatically closed.',
        'EmergencyMode': 'The database is in emergency mode.',
        'Inaccessible': 'The database is inaccessible. The server might'
        ' be switched off or the network connection has been interrupted.',
        'Normal': 'The database is available.',
        'Offline': 'The database has been taken offline.',
        'Recovering': 'The database is going through the recovery process.',
        'RecoveryPending': 'The database is waiting to go through the recovery process.',
        'Restoring': 'The database is going through the restore process.',
        'Shutdown': 'The server on which the database resides has been shut down.',
        'Standby': 'The database is in standby mode.',
        'Suspect': 'The database has been marked as suspect. You will have '
        'to check the data, and the database might have to be restored from a backup.',
    }.get(value, '')


def lookup_database_status(value):
    return {
        'AutoClosed': 1,
        'EmergencyMode': 2,
        'Inaccessible': 4,
        'Normal': 8,
        'Offline': 16,
        'Recovering': 32,
        'RecoveryPending': 64,
        'Restoring': 128,
        'Shutdown': 256,
        'Standby': 512,
        'Suspect': 1024
    }.get(value.strip(), 0)


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
                    'username': username,  # 'sa',
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
    return filter(lambda x: x != "LogonUser succedded", val)


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
    ASSEMBLY_2014 = 'Version=12.0.0.0'
    ASSEMBLY_2016 = 'Version=13.0.0.0'

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

    MSSQL2014_CONNECTION_INFO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Connection,
        ASSEMBLY_2014,
        ASSEMBLY)

    MSSQL2016_CONNECTION_INFO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Connection,
        ASSEMBLY_2016,
        ASSEMBLY)

    MSSQL_CONNECTION_INFO = {9: MSSQL2005_CONNECTION_INFO,
                             10: MSSQL2008_CONNECTION_INFO,
                             11: MSSQL2012_CONNECTION_INFO,
                             12: MSSQL2014_CONNECTION_INFO,
                             13: MSSQL2016_CONNECTION_INFO}

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

    MSSQL2014_SMO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Smo,
        ASSEMBLY_2014,
        ASSEMBLY)

    MSSQL2016_SMO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Smo,
        ASSEMBLY_2016,
        ASSEMBLY)

    MSSQL_SMO = {9: MSSQL2005_SMO,
                 10: MSSQL2008_SMO,
                 11: MSSQL2012_SMO,
                 12: MSSQL2014_SMO,
                 13: MSSQL2016_SMO}

    ASSEMBLY_LOAD_ERROR = "write-host 'assembly load error'"

    sqlConnection = []
    if version not in [9, 10, 11, 12, 13]:
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2016_CONNECTION_INFO)
        sqlConnection.append("}catch{")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2014_CONNECTION_INFO)
        sqlConnection.append("}catch{")
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
        sqlConnection.append("}}}}}")

        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2016_SMO)
        sqlConnection.append("}catch{")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2014_SMO)
        sqlConnection.append("}catch{")
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
        sqlConnection.append("}}}}}")
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


class SqlConnection(object):

    def __init__(self, instance, sqlusername, sqlpassword, login_as_user, version):
        """Build the sql server connection string to establish connection to server
        If using Windows auth, just set instance name and security
        Obfuscate the sql auth password
        """
        self.sqlConnection = []
        self.version = version

        # DB Connection Object
        pwd = base64.b64encode(sqlpassword)
        if login_as_user:
            # use windows auth(SSPI)
            self.sqlConnection.append("$connectionString = 'Data Source={};Integrated Security=SSPI;';".format(instance))
        else:
            # use sql auth
            self.sqlConnection.append("$x = '{}';".format(pwd))
            self.sqlConnection.append("$p = [System.Text.Encoding]::ASCII.GetString([Convert]::FromBase64String($x));")
            self.sqlConnection.append("$connectionString = 'Persist Security Info=False;Data Source={};".format(instance))
            self.sqlConnection.append("User ID={};Password='+$p; ;".format(sqlusername))
        self.sqlConnection.append('$sqlconn = new-object System.Data.SqlClient'
                                  '.SqlConnection($connectionString);')
        self.sqlConnection.append("$con = new-object ('Microsoft.SqlServer"
                                  ".Management.Common.ServerConnection')$sqlconn;")

        # Connect to Database Server
        self.sqlConnection.append("$server = new-object "
                                  "('Microsoft.SqlServer.Management.Smo.Server') $con;")


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


def check_for_network_error(result, config, default_class='/Status/Winrm'):
    '''
    Checks value for timeout/no route to host tracebacks
    '''
    str_result = str(result)
    if 'No route to host' in str_result:
        return 'No route to host {}'.format(config.id), '/Status'

    if 'timeout' in str_result:
        return 'Timeout while connecting to host {}'.format(config.id), '/Status'

    if 'refused' in str_result:
        return 'Connection was refused by other side {}'.format(config.id), '/Status'

    if 'Unauthorized' in str_result:
        return 'Unauthorized, check username and password {}'.format(config.id), '/Status'

    msg = 'Failed collection {0} on {1}'.format(
        result.value.message, config.id
    )

    return msg, default_class


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


def cluster_disk_state_string(state):
    return {-1: 'Unknown',
            0: 'Inherited',
            1: 'Initializing',
            2: 'Online',
            3: 'Offline',
            4: 'Failed',
            128: 'Pending',
            129: 'Online Pending',
            130: 'Offline Pending'}.get(state, 'Undefined')


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


def append_event_datasource_plugin(datasources, events, event):
    event['plugin_classname'] = datasources[0].plugin_classname
    if event not in events:
        events.append(event)


# used to keep track of the number of kerberos error events per device
krb_error_events = {}


def errorMsgCheck(config, events, error):
    """Check error message and generate an appropriate event."""
    if isinstance(error, list):
        error = ' '.join([str(i) for i in error])
    kerberos_messages = ['kerberos', 'kinit']
    wrongCredsMessages = ['Check username and password', 'Username invalid', 'Password expired']

    # see if this a kerberos issue
    if any(x in error.lower() for x in kerberos_messages):
        try:
            threshold = getattr(config.datasources[0], 'zWinRMKRBErrorThreshold', 0)
        except Exception:
            threshold = -1
        global krb_error_events
        if config.id not in krb_error_events:
            krb_error_events[config.id] = 0
        krb_error_events[config.id] += 1
        if krb_error_events[config.id] >= threshold:
            append_event_datasource_plugin(config.datasources, events, {
                'eventClass': '/Status/Kerberos',
                'eventClassKey': 'KerberosFailure',
                'eventKey': '|'.join(('Kerberos', config.id)),
                'summary': error,
                'ipAddress': config.manageIp,
                'severity': 4,
                'device': config.id})
            krb_error_events[config.id] = 0
        return True
    # otherwise check if this is a typical authentication failure
    elif any(x in error for x in wrongCredsMessages):
        append_event_datasource_plugin(config.datasources, events, {
            'eventClass': '/Status/Winrm/Auth',
            'eventClassKey': 'AuthenticationFailure',
            'eventKey': '|'.join(('Authentication', config.id)),
            'summary': error,
            'ipAddress': config.manageIp,
            'severity': 4,
            'device': config.id})
        return True
    return False


def generateClearAuthEvents(config, events):
    """Generate clear authentication events."""
    # reset event counter
    krb_error_events[config.id] = 0
    append_event_datasource_plugin(config.datasources, events, {
        'eventClass': '/Status/Winrm/Auth',
        'eventClassKey': 'AuthenticationSuccess',
        'eventKey': '|'.join(('Authentication', config.id)),
        'summary': 'Authentication Successful',
        'severity': 0,
        'device': config.id})
    append_event_datasource_plugin(config.datasources, events, {
        'eventClass': '/Status/Kerberos',
        'eventClassKey': 'KerberosSuccess',
        'eventKey': '|'.join(('Kerberos', config.id)),
        'summary': 'No Kerberos failures',
        'severity': 0,
        'device': config.id})


def get_dummy_dpconfig(ref_dp, id):
    """Return datapoint config based on reference datapoint config"""
    dp_name = '{}_{}'.format(id, id)
    dp_config = ref_dp.__class__()
    dp_config.__dict__.update(ref_dp.__dict__)
    dp_config.id = id
    dp_config.dpName = dp_name
    dp_config.component = ref_dp.component
    if not isinstance(dp_config.rrdPath, dict):
        dp_config.rrdPath = '/'.join(dp_config.rrdPath.split('/')[:-1] + [dp_name])
    dp_config.rrdType = 'GAUGE'
    return dp_config


def get_dsconf(dsconfs, component, param=None):
    for dsconf in dsconfs:
        if component == dsconf.component:
            return dsconf
        elif component == dsconf.params.get(param, None):
            return dsconf
    return None


def has_metricfacade():
    '''return True if metricfacade can be imported'''
    try:
        from Products.Zuul.facades import metricfacade
    except ImportError:
        pass
    else:
        return True
    return False


HAS_METRICFACADE = has_metricfacade()


def get_rrd_path(obj):
    """Preserve old-style RRD paths"""
    if HAS_METRICFACADE:
        return super(obj.__class__, obj).rrdPath()
    else:
        d = obj.device()
        if not d:
            return "Devices/" + obj.id
        # revert to 2.5 behavior if True
        dmd_root = obj.getDmd()
        if dmd_root and getattr(dmd_root, 'windows_using_legacy_rrd_paths', False):
            skip = len(d.getPrimaryPath()) - 1
            return 'Devices/' + '/'.join(obj.getPrimaryPath()[skip:])
        else:
            return super(obj.__class__, obj).rrdPath()


def keyword_search(root, keywords):
    """Generate objects that match one or more of given keywords."""
    if isinstance(keywords, basestring):
        keywords = [keywords]
    elif isinstance(keywords, set):
        keywords = list(keywords)

    if keywords:
        catalog = ICatalogTool(root)
        query = In('searchKeywords', keywords)
        for result in catalog.search(query=query):
            try:
                yield result.getObject()
            except Exception:
                pass
