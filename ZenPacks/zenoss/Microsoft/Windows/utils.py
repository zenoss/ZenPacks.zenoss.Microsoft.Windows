##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2023, all rights reserved.
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
import logging
from datetime import datetime
import collections
from Products.AdvancedQuery import In
from Products.ZenEvents import ZenEventClasses
from Products.Zuul.interfaces import ICatalogTool
from Products.DataCollector.plugins.DataMaps import ObjectMap

log = logging.getLogger("zen.MicrosoftWindows.utils")

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
    ASSEMBLY_2017 = 'Version=14.0.0.0'
    ASSEMBLY_2019 = 'Version=15.0.0.0'
    ASSEMBLY_2022 = 'Version=16.0.0.0'

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

    MSSQL2017_CONNECTION_INFO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Connection,
        ASSEMBLY_2017,
        ASSEMBLY)

    MSSQL2019_CONNECTION_INFO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Connection,
        ASSEMBLY_2019,
        ASSEMBLY)

    MSSQL2022_CONNECTION_INFO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Connection,
        ASSEMBLY_2022,
        ASSEMBLY)

    MSSQL_CONNECTION_INFO = {9: MSSQL2005_CONNECTION_INFO,
                             10: MSSQL2008_CONNECTION_INFO,
                             11: MSSQL2012_CONNECTION_INFO,
                             12: MSSQL2014_CONNECTION_INFO,
                             13: MSSQL2016_CONNECTION_INFO,
                             14: MSSQL2017_CONNECTION_INFO,
                             15: MSSQL2019_CONNECTION_INFO,
                             16: MSSQL2022_CONNECTION_INFO}

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

    MSSQL2017_SMO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Smo,
        ASSEMBLY_2017,
        ASSEMBLY)

    MSSQL2019_SMO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Smo,
        ASSEMBLY_2019,
        ASSEMBLY)

    MSSQL2022_SMO = '{0}, {1}, {2} -EA Stop'.format(
        ASSEMBLY_Smo,
        ASSEMBLY_2022,
        ASSEMBLY)

    MSSQL_SMO = {9: MSSQL2005_SMO,
                 10: MSSQL2008_SMO,
                 11: MSSQL2012_SMO,
                 12: MSSQL2014_SMO,
                 13: MSSQL2016_SMO,
                 14: MSSQL2017_SMO,
                 15: MSSQL2019_SMO,
                 16: MSSQL2022_SMO}

    ASSEMBLY_LOAD_ERROR = "write-host 'assembly load error'"

    sqlConnection = []
    if version not in [9, 10, 11, 12, 13, 14, 15, 16]:
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2022_CONNECTION_INFO)
        sqlConnection.append("}catch{")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2019_CONNECTION_INFO)
        sqlConnection.append("}catch{")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2017_CONNECTION_INFO)
        sqlConnection.append("}catch{")
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
        sqlConnection.append("}}}}}}}}")

        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2022_SMO)
        sqlConnection.append("}catch{")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2019_SMO)
        sqlConnection.append("}catch{")
        sqlConnection.append("try{")
        sqlConnection.append(MSSQL2017_SMO)
        sqlConnection.append("}catch{")
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
        sqlConnection.append('}}}}}}}}')
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
    if getattr(item, 'CommandLine', None):
        item.CommandLine = item.CommandLine.strip('"')

    return getattr(item, 'CommandLine', None) or\
        getattr(item, 'ExecutablePath', None) or\
        getattr(item, 'Name', '')


def get_processNameAndArgs(item):
    '''
    Return (name, args) tuple given a Win32_Process item.
    '''
    name = getattr(item, 'ExecutablePath', None) or getattr(item, 'Name', '')
    if getattr(item, 'CommandLine', None):
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

    msg = 'Failed collection with message: "{0}" on {1}'.format(
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


def cluster_csv_state_to_disk_map(state):
    return {'Online': 2,
            'Up': 2,
            'Offline': 3,
            'PartialOnline': 129,
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


def get_console_output_from_parts(parts):
    if isinstance(parts, (list, tuple)):
        output = '\n'.join(parts)
    else:
        output = parts
    return output


def parse_winrs_response(winrs_response, parsing_format='json'):
    """
    Parses response from Windows remote shell

    @param winrs_response: logger.
    @type winrs_response: Union[list, tuple, string]
    @param parsing_format: String with parsing format name.
    @type parsing_format: str

    @return: tuple with parsed result and error message (if present)
    @rtype: tuple
    """

    result = None
    error = None

    if not isinstance(parsing_format, basestring):
        error = 'parsing format should be string'
        return result, error

    supprted_formats = ('json',)

    if parsing_format.lower() in supprted_formats:
        try:
            winrs_response_joined = get_console_output_from_parts(winrs_response)
            result = json.loads(
                winrs_response_joined
            )
        except (ValueError, TypeError, IndexError, KeyError) as e:
            error = e.message
    else:
        error = 'Unsupported parsing format. Currently supported formats: {}'.format(','.join(supprted_formats))

    return result, error


def get_sql_instance_naming_info(instance_name, is_cluster_instance=False, hostname='', cluster_instance_name=''):
    """
    Return proper SQL Instance title and full SQL Instance name depends on provided parameters.

    @param instance_name: SQL Instance name.
    @type instance_name: str
    @param is_cluster_instance: Whether it is Cluster SQL Instance. Default is False
    @type is_cluster_instance: bool
    @param hostname: Non-cluster SQL Instance hostname. Default is empty string.
    @type hostname: str
    @param cluster_instance_name: Name of Cluster SQL Instance. Default is empty string.
    @type cluster_instance_name: str

    @return: Tuple (instance_title, full_sql_instance_name)
    @rtype: tuple
    """
    instance_title = instance_name

    if is_cluster_instance:
        if instance_name == 'MSSQLSERVER':
            instance_title = full_sql_instance_name = cluster_instance_name
        else:
            full_sql_instance_name = '{0}\{1}'.format(cluster_instance_name, instance_name)
    else:
        if instance_name == 'MSSQLSERVER':
            instance_title = full_sql_instance_name = hostname
        else:
            full_sql_instance_name = '{0}\{1}'.format(hostname, instance_name)

    return instance_title, full_sql_instance_name


def get_sql_instance_original_name(instance_name, instance_hostname):
    """
    Return proper SQL Instance original name. Is useful when dealing with Default MS SQL Instances ('MSSQLSERVER').
    In scope of local resources - Default instances retains 'MSSQLSERVER'. But when information is cross-nodes - these
    instances are named after their hosted nodes (e.g node1, node2). This function returns 'MSSQLSERVER' when Instance
    name is equal to its hostname.

    @param instance_name: SQL Instance name.
    @type instance_name: str
    @param instance_hostname: SQL Instance hostname.
    @type instance_hostname: str

    @return: SQL Instance name as local resource.
    @rtype: str
    """
    instance_original_name = instance_name

    if not isinstance(instance_name, basestring) or not isinstance(instance_hostname, basestring):
        return instance_original_name

    if instance_name.lower().strip() == instance_hostname.lower().strip():
        instance_original_name = 'MSSQLSERVER'

    return instance_original_name


def get_proper_sql_instance_full_name(instance_full_name, is_cluster_instance, hostname='', cluster_instance_name=''):
    """
    Get proper instance full name by filter out default SQL Instance name ('MSSQLSERVER')
    """
    proper_sql_instance_full_name = instance_full_name

    if is_cluster_instance:
        if instance_full_name == 'MSSQLSERVER':
            proper_sql_instance_full_name = cluster_instance_name
    else:
        if instance_full_name == 'MSSQLSERVER':
            proper_sql_instance_full_name = hostname

    return proper_sql_instance_full_name


def use_sql_always_on(device):
    """
    Determines whether to use SQL Always On functionality based on information taken from provided Device proxy.
    Currently Always On is used for Microsoft/Cluster devices with enabled zSQLAlwaysOnEnabled zProperty.

    @param device: Device proxy.
    @type device: Products.DataCollector.DeviceProxy.DeviceProxy

    @return: Boolean, whether to use SQL Always On
    @rtype: bool
    """

    sql_always_on_enabled = getattr(device, 'zSQLAlwaysOnEnabled', False)
    device_class_name = getattr(device, 'getDeviceClassName', '')

    return sql_always_on_enabled and 'Microsoft/Cluster' in device_class_name


def get_ao_sql_instance_id(prep_id_method, instance_name='', is_cluster_sql_instnace=False, instance_hostnmane='',
                           sql_server_instance_full_name=''):
    """
    Returns SQL Instance ID to be use in Zenoss component path. If valid sql_server_instance_full_name is provided - it
    will used straightaway (with prep_id_method processing)
    """

    # If sql_server_instance_full_name is provided - use it straightaway
    if isinstance(sql_server_instance_full_name, basestring) and sql_server_instance_full_name:
        return prep_id_method(sql_server_instance_full_name)

    if not isinstance(is_cluster_sql_instnace, bool) or \
            not prep_id_method or \
            not instance_name:
        return None

    if not is_cluster_sql_instnace and not instance_hostnmane:
        return None

    if is_cluster_sql_instnace:
        name_for_id = instance_name
    else:
        name_for_id = '{}_{}'.format(instance_hostnmane, instance_name)

    return prep_id_method(name_for_id)


def lookup_cluster_member_state(value):
    return {
        0: 'Offline',
        1: 'Online',
        2: 'Partially Online',
        3: 'Unknown',
    }.get(value, 'unknown')


def lookup_failover_cluster_resource_state(value):
    return {
        0: 'Inherited',
        1: 'Initializing',
        2: 'Online',
        3: 'Offline',
        4: 'Failed',
        128: 'Pending',
        129: 'OnlinePending',
        130: 'OfflinePending',
        -1: 'Unknown'
    }.get(value, 'unknown')


def lookup_ag_state(value):
    return {
        0: 'Offline',
        1: 'Online',
    }.get(value, 'unknown')


def lookup_ag_synchronization_health(value):
    return {
        0: 'Not healthy',
        1: 'Partially healthy',
        2: 'Healthy',
    }.get(value, 'unknown')


def lookup_ag_automated_backup_preference(value):
    return {
        0: 'Primary',
        1: 'Secondary only',
        2: 'Prefer Secondary',
        3: 'Any Replica',
    }.get(value, 'unknown')


def lookup_ag_primary_recovery_health(value):
    return {
        0: 'In progress',
        1: 'Online',
    }.get(value, 'unknown')


def lookup_ag_failure_condition_level(value):
    return {
        1: 'OnServerDown',
        2: 'OnServerUnresponsive',
        3: 'OnCriticalServerErrors',
        4: 'OnModerateServerErrors',
        5: 'OnAnyQualifiedFailureCondition',
        6: 'Unknown',
    }.get(value, 'unknown')


def lookup_ag_cluster_type(value):
    return {
        0: 'WSFC',
        1: 'None',
        2: 'External',
    }.get(value, 'unknown')


def lookup_ag_quorum_state(value):
    return {
        0: 'Unknown quorum state',
        1: 'Normal quorum',
        2: 'Forced quorum',
    }.get(value, 'unknown')


def fill_ag_om(ag_om, ag_data, prep_id_method, sql_instance_data):
    """
    Fill ObjectMaps for Always On Availability Group.
    """
    for key, value in ag_data.iteritems():
        if key == 'id':
            setattr(ag_om, 'unigue_id', value)
            continue  # Do not use AG internal SQL id as in case of all SQL Instance outage - AG will be deleted.
            # use AG Cluster resource id instead:
        if key == 'ag_res_id':
            setattr(ag_om, 'id', prep_id_method(value))
        if key == 'name':
            setattr(ag_om, 'title', value)
            continue
        if key == 'synchronization_health':
            value = lookup_ag_synchronization_health(value)
        if key == 'automated_backup_preference':
            value = lookup_ag_automated_backup_preference(value)
        if key == 'primary_recovery_health':
            value = lookup_ag_primary_recovery_health(value)
        if key == 'failure_condition_level':
            value = lookup_ag_failure_condition_level(value)
        if key == 'cluster_type':
            value = lookup_ag_cluster_type(value)
        if key in ('primary_replica_server_name', 'is_clustered_instance'):
            continue  # relation to SQL Instance is set below.
        setattr(ag_om, key, value)

    sql_server_instance_full_name = sql_instance_data.get('sql_server_fullname') \
                                    or ag_data.get('primary_replica_server_name')
    sql_instance_name = sql_instance_data.get('sql_instance_name') or ag_data.get('sql_instance_name')
    is_clustered_instance = sql_instance_data.get('is_clustered_instance') or ag_data.get('is_clustered_instance') \
                            or False
    sql_hostname = sql_instance_data.get('sql_hostname') or ag_data.get('sql_hostname')

    sql_instance_id = get_ao_sql_instance_id(prep_id_method,
                                             sql_instance_name,
                                             is_clustered_instance,
                                             sql_hostname,
                                             sql_server_instance_full_name)
    if sql_instance_id:
        setattr(ag_om, 'set_winsqlinstance', sql_instance_id)

    quorum_state = sql_instance_data.get('quorum_state')
    if quorum_state:
        setattr(ag_om, 'quorum_state', quorum_state)

    return ag_om


def lookup_ar_role(value):
    return {
        0: 'Resolving',
        1: 'Primary',
        2: 'Secondary',
        3: 'Unknown'
    }.get(value, 'unknown')


def lookup_ar_operational_state(value):
    return {
        0: 'Pending failover',
        1: 'Pending',
        2: 'Online',
        3: 'Offline',
        4: 'Failed',
        5: 'Failed no Quorum',
        6: 'Unknown'
    }.get(value, 'unknown')


def lookup_ar_availability_mode(value):
    return {
        0: 'Asynchronous commit',
        1: 'Synchronous commit',
        2: 'Unknown',
        4: 'Configuration only'
    }.get(value, 'unknown')


def lookup_ar_connection_state(value):
    return {
        0: 'Disconnected',
        1: 'Connected',
        2: 'Unknown'
    }.get(value, 'unknown')


def lookup_ar_synchronization_state(value):
    return {
        0: 'Not synchronizing',
        1: 'Synchronizing',
        2: 'Synchronized',
        3: 'Unknown'
    }.get(value, 'unknown')


def lookup_ar_failover_mode(value):
    return {
        0: 'Automatic',
        1: 'Manual',
        2: 'External',
        3: 'Unknown'
    }.get(value, 'unknown')


def lookup_ar_synchronization_health(value):
    return {
        0: 'Not healthy',
        1: 'Partially healthy',
        2: 'Healthy'
    }.get(value, 'unknown')


def lookup_adb_sync_state(value):
    return {
        0: 'Not Synchronizing',
        1: 'Synchronizing',
        2: 'Synchronized',
        3: 'Reverting',
        4: 'Initializing',
    }.get(value, 'unknown')


def get_ag_severities(prop_name, prop_value):
    """
    Returns ZenEventClasses severity for given MS SQL Always On Availability Group property and its value.
    """
    ag_severities_map = {
        'synchronization_health': {
            'Not healthy': ZenEventClasses.Critical,
            'Partially healthy': ZenEventClasses.Warning,
            'Healthy': ZenEventClasses.Clear,
        },
        'quorum_state': {
            'Unknown quorum state': ZenEventClasses.Warning,
            'Normal quorum': ZenEventClasses.Clear,
            'Forced quorum': ZenEventClasses.Warning,
        }
    }

    return ag_severities_map.get(prop_name, {}).get(prop_value, ZenEventClasses.Warning)


def get_ar_severities(prop_name, prop_value):
    """
    Returns ZenEventClasses severity for given MS SQL Always On Availability Replica property and its value.
    """
    ar_severities_map = {
        'state': {
            'Online': ZenEventClasses.Clear,
            'Offline': ZenEventClasses.Critical,
            'Partially Online': ZenEventClasses.Warning,
            'Unknown': ZenEventClasses.Warning
        },
        'role': {
            'Primary': ZenEventClasses.Clear,
            'Secondary': ZenEventClasses.Clear,
            'Resolving': ZenEventClasses.Clear,
            'Unknown': ZenEventClasses.Warning
        },
        'operational_state': {
            'Online': ZenEventClasses.Clear,
            'Offline': ZenEventClasses.Critical,
            'Pending': ZenEventClasses.Info,
            'Pending failover': ZenEventClasses.Warning,
            'Failed': ZenEventClasses.Critical,
            'Failed no Quorum': ZenEventClasses.Critical,
            'Unknown': ZenEventClasses.Warning
        },
        'connection_state': {
            'Connected': ZenEventClasses.Clear,
            'Disconnected': ZenEventClasses.Critical,
            'Unknown': ZenEventClasses.Warning
        },
        'synchronization_state': {
            'Synchronizing': ZenEventClasses.Clear,
            'Synchronized': ZenEventClasses.Clear,
            'Not synchronizing': ZenEventClasses.Critical,
            'Unknown': ZenEventClasses.Warning
        },
        'synchronization_health': {
            'Healthy': ZenEventClasses.Clear,
            'Partially healthy': ZenEventClasses.Warning,
            'Not healthy': ZenEventClasses.Critical
        }
    }

    return ar_severities_map.get(prop_name, {}).get(prop_value, ZenEventClasses.Warning)


def get_al_severities(prop_name, prop_value):
    """
    Returns ZenEventClasses severity for given MS SQL Always On Availability Listener property and its value.
    """
    al_severities_map = {
        'state': {
            'Inherited': ZenEventClasses.Info,
            'Initializing': ZenEventClasses.Info,
            'Online': ZenEventClasses.Clear,
            'Offline': ZenEventClasses.Critical,
            'Failed': ZenEventClasses.Critical,
            'Pending': ZenEventClasses.Info,
            'OnlinePending': ZenEventClasses.Info,
            'OfflinePending': ZenEventClasses.Warning,
            'Unknown': ZenEventClasses.Warning,
        }
    }

    return al_severities_map.get(prop_name, {}).get(prop_value, ZenEventClasses.Warning)


def get_adb_severities(prop_name, prop_value):
    """
    Returns ZenEventClasses severity for given MS SQL Always On protected Databases properties and its values.
    """

    if isinstance(prop_value, bool):
        try:
            prop_value = str(prop_value)  # Cast to string to avoid different variants of value type
        except (TypeError, ValueError):
            pass

    if isinstance(prop_value, int):
        max_db_status = max(get_db_bit_statuses(prop_value))
        prop_value = DB_STATUSES.get(max_db_status)

    adb_severities_map = {
        'status': {
            'AutoClosed': ZenEventClasses.Info,
            'EmergencyMode': ZenEventClasses.Warning,
            'Inaccessible': ZenEventClasses.Warning,
            'Normal': ZenEventClasses.Clear,
            'Offline': ZenEventClasses.Critical,
            'Recovering': ZenEventClasses.Info,
            'RecoveryPending': ZenEventClasses.Info,
            'Restoring': ZenEventClasses.Info,
            'Shutdown': ZenEventClasses.Info,
            'Standby': ZenEventClasses.Info,
            'Suspect': ZenEventClasses.Warning
        },
        'suspended': {
            'True': ZenEventClasses.Warning,
            'False': ZenEventClasses.Clear
        },
        'sync_state': {
            'Not Synchronizing': ZenEventClasses.Critical,
            'Synchronizing': ZenEventClasses.Clear,
            'Synchronized': ZenEventClasses.Clear,
            'Reverting': ZenEventClasses.Info,
            'Initializing': ZenEventClasses.Info,
        }
    }

    return adb_severities_map.get(prop_name, {}).get(prop_value, ZenEventClasses.Warning)


def get_prop_value_events(component_class_name, values_source, event_info):
    """
    Returns a list with dicts as representation of events. The purpose of the func is to get full information about
    certain properties event and severities, based on the properties value. Event is created for each property.

    @param component_class_name: Name of component class.
    @type component_class_name: str
    @param values_source: Dict or other mapping with properties as keys and their values.
    @type values_source: dict or other mapping
    @param event_info: Dict or other mapping with the information about required for event:
        {
            'event_class': '',
            'event_key': '',
            'device': '',
            'component': '',
            'component_title': '',
        }
    @type event_info: dict or other mapping

    @return: List with dicts as representation of each event
    @rtype: list
    """

    event_list = []

    if not isinstance(component_class_name, basestring):
        return event_list

    component_info = {
        'WinSQLAvailabilityGroup': {
            'properties': (('synchronization_health', 'Synchronization Health'),
                           ('quorum_state', 'Quorum State')),
            'event_class_key': 'AOAvailabilityGroupPropChange {}',
            'event_summary': '{} of Availability Group {} is {}',
            'get_severities_func': get_ag_severities,
        },
        'WinSQLAvailabilityReplica': {
            'properties': (('state', 'State'),
                           ('role', 'Role'),
                           ('operational_state', 'Operational State'),
                           ('connection_state', 'Connection State'),
                           ('synchronization_state', 'Synchronization State'),
                           ('synchronization_health', 'Synchronization Health')),
            'event_class_key': 'AOAvailabilityReplicaPropChange {}',
            'event_summary': '{} of Availability Replica {} is {}',
            'get_severities_func': get_ar_severities,
        },
        'WinSQLAvailabilityListener': {
            'properties': (('state', 'State'),),
            'event_class_key': 'AOAvailabilityListenerPropChange {}',
            'event_summary': '{} of Availability Listener {} is {}',
            'get_severities_func': get_al_severities,
        },
        'WinSQLDatabase': {
            'properties': (('status', 'Database Status'),
                           ('suspended', 'Suspended'),
                           ('sync_state', 'Synchronization State')),
            'event_class_key': 'AOWinSQLDatabasePropChange {}',
            'event_summary': '{} of SQL Database {} is {}',
            'get_severities_func': get_adb_severities,
        }
    }

    component_properties = component_info.get(component_class_name, {}).get('properties')
    get_severities_func = component_info.get(component_class_name, {}).get('get_severities_func')
    if not component_properties or not get_severities_func:
        return event_list

    event_class_key = component_info.get(component_class_name, {}).get('event_class_key', '')
    event_summary = component_info.get(component_class_name, {}).get('event_summary', '{} {} {}')
    event_class = event_info.get('event_class', '/Status')
    event_key = event_info.get('event_key')
    device = event_info.get('device')
    component = event_info.get('component')
    component_title = event_info.get('component_title')

    for prop_name, prop_title in component_properties:
        prop_value = values_source.get(prop_name)
        event_list.append(
            dict(
                eventClass=event_class,
                eventClassKey=event_class_key.format(prop_name),
                eventKey=event_key or '{} change'.format(prop_name),
                severity=get_severities_func(prop_name, prop_value),
                summary=event_summary.format(prop_title, component_title, prop_value),
                device=device,
                component=component
            )
        )

    return event_list


def get_default_properties_value_for_component(component_class_name):
    """
    Returns dict with properties which are minimum required for particular component class and their default values.
    One possible usage of this func is to return some data in case when component is unreachable during collection.

    @param component_class_name: Name of component class.
    @type component_class_name: str

    @return: Dict, where properties are keys and values - default property value.
    @rtype: dict
    """
    if not isinstance(component_class_name, basestring):
        return {}

    default_prop_values = {
        'WinSQLAvailabilityGroup': {
            'synchronization_health': '',
            'primary_recovery_health': '',
            'quorum_state': ''
        },
        'WinSQLAvailabilityReplica': {
            'state': '',
            'role': '',
            'operational_state': '',
            'connection_state': '',
            'synchronization_state': '',
            'synchronization_health': '',
            'failover_mode': '',
            'availability_mode': ''
        },
        'WinSQLAvailabilityListener': {
            'state': None
        },
        'WinSQLDatabase': {
            'sync_state': '',
            'status': ''
        }
    }

    return default_prop_values.get(component_class_name, {})


def fill_ar_om(om, data, prep_id_method, sql_instance_data):
    """
    Fill ObjectMaps for Always On Availability Replica.
    """
    for key, value in data.iteritems():
        if key == 'id':
            setattr(om, 'unigue_id', value)
            value = prep_id_method(value)
        if key == 'name':
            setattr(om, 'title', value)
            continue
        if key == 'role':
            value = lookup_ar_role(value)
        if key == 'state':
            value = lookup_cluster_member_state(value)
        if key == 'operational_state':
            value = lookup_ar_operational_state(value)
        if key == 'availability_mode':
            value = lookup_ar_availability_mode(value)
        if key == 'connection_state':
            value = lookup_ar_connection_state(value)
        if key == 'synchronization_state':
            value = lookup_ar_synchronization_state(value)
        if key == 'failover_mode':
            value = lookup_ar_failover_mode(value)
        if key == 'synchronization_health':
            value = lookup_ar_synchronization_health(value)
        setattr(om, key, value)

    sql_server_instance_full_name = sql_instance_data.get('sql_server_fullname') \
                                    or data.get('replica_server_name')
    sql_instance_name = sql_instance_data.get('sql_instance_name') or data.get('sql_instance_name')
    is_clustered_instance = sql_instance_data.get('is_clustered_instance') or data.get('is_clustered_instance') \
                            or False
    sql_hostname = sql_instance_data.get('sql_hostname') or data.get('sql_hostname')

    sql_instance_id = get_ao_sql_instance_id(prep_id_method,
                                             sql_instance_name,
                                             is_clustered_instance,
                                             sql_hostname,
                                             sql_server_instance_full_name)
    if sql_instance_id:
        setattr(om, 'set_winsqlinstance', sql_instance_id)

    return om


def fill_al_om(om, data, prep_id_method):
    """
    Fill ObjectMaps for Always On Availability Listener.
    """
    for key, value in data.iteritems():
        if key == 'id':
            setattr(om, 'unigue_id', value)
            value = prep_id_method(value)
        if key == 'name':
            setattr(om, 'title', value)
            continue
        if key == 'state':
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = None
            value = lookup_failover_cluster_resource_state(value)
        setattr(om, key, value)

    return om


def fill_adb_om(om, data, prep_id_method):
    """
    Fill ObjectMaps for Always On Availability Database.
    """
    adb_owner_id = data.get('adb_owner_id')
    db_id = data.get('db_id')
    if adb_owner_id and db_id:
        if isinstance(adb_owner_id, basestring):
            setattr(om, 'id', prep_id_method('{}{}'.format(adb_owner_id, db_id)))

    sql_hostname_fqdn = data.get('sql_hostname_fqdn')
    sql_server_name = data.get('sql_server_name')
    if sql_hostname_fqdn and sql_server_name:
        setattr(om, 'cluster_node_server', '{0}//{1}'.format(sql_hostname_fqdn, sql_server_name))

    db_name = data.get('name', '')
    if db_name:
        setattr(om, 'title', db_name)

    keys_to_skip = ('adb_owner_id', 'sql_hostname_fqdn', 'sql_server_name', 'status', 'name')

    keys_values_transform = {
        'keys': {
            'adb_id': 'unigue_id',
            'db_replica_id': 'set_winsqlavailabilityreplica'
        },
        'values': {
            'lastlogbackupdate': get_datetime_string_from_timestamp,
            'lastbackupdate': get_datetime_string_from_timestamp,
            'createdate': get_datetime_string_from_timestamp,
            'sync_state': lookup_adb_sync_state,
            'db_replica_id': prep_id_method
        }
    }

    for key, value in data.iteritems():
        if key in keys_to_skip:
            continue  # we already utilized them

        value_transform_func = keys_values_transform['values'].get(key)  # values first to preserve original keys names
        if value_transform_func and callable(value_transform_func):
            value = value_transform_func(value)

        key = keys_values_transform['keys'].get(key, key)  # if key doesn't have transformation variant - leave it as is

        setattr(om, key, value)

    return om


def recursive_mapping_update(update_destination, update_source):
    """
    Similar to update() method of mapping, but perform it recursively.
    """

    if not all((isinstance(update_destination, collections.Mapping),
               isinstance(update_source, collections.Mapping))):
        return

    def _recursive_mapping_update(_update_destination, _update_source):
        for key, value in _update_source.items():
            if isinstance(value, collections.Mapping):
                _update_destination[key] = _recursive_mapping_update(_update_destination.get(key, {}), value)
            else:
                _update_destination[key] = value
        return _update_destination

    _recursive_mapping_update(update_destination, update_source)


def get_datetime_string_from_timestamp(timestamp, fmt='%Y/%m/%d %H:%M:%S'):
    result = ''
    try:
        tmstmp = float(timestamp)
    except (TypeError, ValueError):
        tmstmp = 0
    if tmstmp > 0:
        result = datetime.fromtimestamp(tmstmp).strftime(fmt)
    return result


def get_db_monitored(db_status, ignored_db_statuses):
    """
    Define whether Database in statuses, which shouldn't be monitored.
    :return: Boolean
    """
    ignored_db_status_names = (status.lower().strip() for status in ignored_db_statuses)
    if db_status:
        for bit_status in get_db_bit_statuses(db_status):
            status_name = DB_STATUSES.get(int(bit_status), '').lower()
            if not status_name:
                log.warning("The status code - [{}] does not match any status that is known to ZenPack. "
                            "Skipped check for ignored DB statuses.".format(db_status))
            if status_name in ignored_db_status_names:
                return False
    return True


def get_db_om(datasource_config, data):
    """
    Fill ObjectMaps for Database.
    """
    db_om = ObjectMap()
    db_om.id = datasource_config.params['instanceid']
    db_om.title = datasource_config.params['contexttitle']
    db_om.compname = datasource_config.params['contextcompname']
    db_om.modname = datasource_config.params['contextmodname']
    db_om.relname = datasource_config.params['contextrelname']
    for key, value in data.iteritems():
        if key == 'status':
            is_monitored = get_db_monitored(value, datasource_config.params.get('db_ignored_statuses', []))
            setattr(db_om, 'monitor', is_monitored)
    return db_om


def get_db_bit_statuses(value):
    statuses = []

    for bit in sorted(DB_STATUSES.keys()):
        if value & bit:
            statuses.append(bit)

    return statuses
