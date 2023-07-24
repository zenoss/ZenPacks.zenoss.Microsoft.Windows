##############################################################################
#
# Copyright (C) Zenoss, Inc. 2019, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from ZenPacks.zenoss.Microsoft.Windows.tests.utils import ItemBuilder

from Products.ZenTestCase.BaseTestCase import BaseTestCase

from ZenPacks.zenoss.Microsoft.Windows.utils import get_processText, get_processNameAndArgs, get_sql_instance_original_name


process_wmi_data = {
    'win32_process': [
        {
            'ExecutablePath': 'C:\\Windows\\system32\\wbem\\wmiprvse.exe',
            'Name': 'WmiPrvSE.exe'
        }, {
            'CommandLine': None,
            'ExecutablePath': None,
            'Name': 'System Idle Process',
        }, {
            'CommandLine': 'C:\\Windows\\system32\\WinrsHost.exe -Embedding',
            'ExecutablePath': 'C:\\Windows\\system32\\WinrsHost.exe',
            'Name': 'winrshost.exe',
        }, {
            'CommandLine': '\\??\\C:\\Windows\\system32\\conhost.exe 0x4',
            'ExecutablePath': 'C:\\Windows\\system32\\conhost.exe',
            'Name': 'conhost.exe',
        }, {
            'CommandLine': '''C:\\Windows\\system32\\cmd.exe /C powershell -NoLogo -NonInteractive -NoProfile -OutputFormat TEXT -Command "& {$Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size (496, 512);try{add-type -AssemblyName 'Microsoft.SqlServer.ConnectionInfo, Version=13.0.0.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91' -EA Stop}catch{try{add-type -AssemblyName 'Microsoft.SqServer.ConnectionInfo, Version=12.0.0.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91' -EA Stop}catch{try{add-type -AssemblyName 'Microsoft.SqlServer.ConnectionInfo, Version=11.0.0.0, Culture=eutral, PublicKeyToken=89845dcd8080cc91' -EA Stop}catch{try{add-type -AssemblyName 'Microsoft.SqlServer.ConnectionInfo, Version=10.0.0.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91' -EA Stopcatch{try{add-type -AssemblyName 'Microsoft.SqlServer.ConnectionInfo, Version=9.0.242.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91'}catch{write-host 'assembly load error'}}}}}try{add-type -ssemblyName 'Microsoft.SqlServer.Smo, Version=13.0.0.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91' -EA Stop}catch{try{add-type -AssemblyName 'Microsoft.SqlServer.Smo, Version=12.0.0.0, Cultre=neutral, PublicKeyToken=89845dcd8080cc91' -EA Stop}catch{try{add-type -AssemblyName 'Microsoft.SqlServer.Smo, Version=11.0.0.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91' -EA Stop}catch{ry{add-type -AssemblyName 'Microsoft.SqlServer.Smo, Version=10.0.0.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91' -EA Stop}catch{try{add-type -AssemblyName 'Microsoft.SqlServer.Smo, Version=.0.242.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91'}catch{write-host 'assembly load error'}}}}}$con = new-object ('Microsoft.SqlServer.Management.Common.ServerConnection')'win2016-node-01' 'solutions', 'Z3n0ssQA';$con.LoginSecure=$true;$con.ConnectAsUser=$true;$con.ConnectAsUserName='solutions';$con.ConnectAsUserPassword='Z3n0ssQA';$server = new-object ('Microsoft.SqlServer.Managemnt.Smo.Server') $con;if ($server.Databases -ne $null) {$dbMaster = $server.Databases['master'];foreach ($db in $server.Databases){$db_name = '';$sp = $db.Name.split($([char]39)); if($sp.length -ge2){ foreach($i in $sp){ if($i -ne $sp[-1]){ $db_name += $i + [char]39 + [char]39;}else { $db_name += $i;}}} else { $db_name = $db.Name;}$query = 'select instance_name as databasename, counter_nameas ckey, cntr_value as cvalue from sys.dm_os_performance_counters where instance_name = ' +[char]39+$db_name+[char]39;$ds = $dbMaster.ExecuteWithResults($query);if($ds.Tables[0].rows.count -gt 0) $ds.Tables| Format-List;}Write-Host "databasename:"$db_name;$status = $db.Status;write-host "databasestatus:"$status;}}}"''',
            'ExecutablePath': 'C:\\Windows\\system32\\cmd.exe',
            'Name': 'cmd.exe'}]}


class TestUtils(BaseTestCase):
    """Test windows utils."""

    def setUp(self):
        """Initial set up of tests."""
        self.ib = ItemBuilder()
        self.process_results = self.ib.create_results(process_wmi_data)

    def test_get_process_text(self):
        """Test get_processText."""
        win32_process = self.process_results['win32_process']
        for item in win32_process:
            text = get_processText(item)
            if getattr(item, 'CommandLine', None):
                self.assertEquals(text, item.CommandLine)
            elif getattr(item, 'ExecutablePath', None):
                self.assertEquals(text, item.ExecutablePath)
            else:
                self.assertEquals(text, item.Name)

    def test_get_process_name_args(self):
        """Test get_processText."""
        win32_process = self.process_results['win32_process']
        for item in win32_process:
            name, args = get_processNameAndArgs(item)
            if getattr(item, 'ExecutablePath', None):
                self.assertEquals(name, item.ExecutablePath)
            else:
                self.assertEquals(name, item.Name)
            if getattr(item, 'CommandLine', None):
                command_line = item.CommandLine.strip('"')
                expected_args = command_line.replace(
                    name, '', 1).strip()
                self.assertEquals(args, expected_args)
            else:
                self.assertEquals(args, '')

    def test_get_sql_instance_original_name_default(self):
        """Test get SQL Instance original name with a default behavior."""
        instance_name = 'MSSQLSERVER'
        instance_hostname = 'hostname_1'
        instance_original_name = get_sql_instance_original_name(instance_name, instance_hostname)
        self.assertEquals(instance_original_name, 'MSSQLSERVER')

    def test_get_sql_instance_original_name_empty_instance_hostname(self):
        """Test get SQL Instance original name with an empty instance hostname."""
        instance_name = 'MSSQLSERVER'
        instance_hostname = None
        instance_original_name = get_sql_instance_original_name(instance_name, instance_hostname)
        self.assertEquals(instance_original_name, 'MSSQLSERVER')

    def test_get_sql_instance_original_name_empty_all_data(self):
        """Test get SQL Instance original name with an empty instance name and instance hostname."""
        instance_name = None
        instance_hostname = None
        instance_original_name = get_sql_instance_original_name(instance_name, instance_hostname)
        self.assertEquals(instance_original_name, None)


def test_suite():
    """Return test suite for this module."""
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestUtils))
    return suite


if __name__ == "__main__":
    from zope.testrunner.runner import Runner
    runner = Runner(found_suites=[test_suite()])
    runner.run()
