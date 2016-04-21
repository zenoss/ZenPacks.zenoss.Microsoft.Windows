##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Windows Installed Software

Models list of installed software by querying registry.
Querying Win32_Product causes Windows installer to run a consistency check,
possibly causing other problems to appear.
"""

from DateTime import DateTime
from DateTime.interfaces import SyntaxError, TimeError

from Products.DataCollector.plugins.DataMaps import MultiArgs

from OFS.ObjectManager import checkValidId, BadRequest

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import save


class Software(WinRMPlugin):
    compname = 'os'
    relname = 'software'
    modname = 'Products.ZenModel.Software'

    powershell_commands = dict(
        software=(
            "Get-ChildItem -Path HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            " | ForEach-Object {'DisplayName='+$_.GetValue('DisplayName')+';InstallDate='+"
            " $_.GetValue('InstallDate')+';Vendor='+$_.GetValue('Publisher'), '|'}; "
            "Get-ChildItem -Path HKLM:\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            " | ForEach-Object {'DisplayName='+$_.GetValue('DisplayName')+';InstallDate='+"
            " $_.GetValue('InstallDate')+';Vendor='+$_.GetValue('Publisher'), '|'}; "
        )
    )

    @save
    def process(self, device, results, log):
        # data format expected in results
        # DisplayName=Software1;InstallDate=19700101;Vendor=Microsoft Corporation|
        # DisplayName=Software2;InstallDate=19700102;Vendor=Microsoft Corporation|
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        rm = self.relMap()

        software_results = results.get('software')
        if not software_results:
            return rm

        software_results = ''.join(software_results.stdout).split('|')

        # Registry Software formatting
        for sw in software_results:
            softwareDict = {}
            for keyvalues in sw.split(';'):
                try:
                    key, value = keyvalues.split('=')
                except ValueError:
                    continue
                try:
                    if key == "Vendor":
                        checkValidId(None, value, allow_dup=False)
                except BadRequest:
                    value = str()
                softwareDict[key] = value

            keys = ['DisplayName', 'Vendor', 'InstallDate']
            # malformed data line
            if set(keys).difference(set(softwareDict.keys())):
                continue
            # skip over empty entries
            if softwareDict['DisplayName'] == '':
                continue
            om = self.objectMap()
            om.id = self.eliminate_underscores(self.prepId(softwareDict['DisplayName'])).strip()
            vendor = softwareDict['Vendor'].strip() if softwareDict['Vendor'].strip() != '' else 'Unknown'

            om.setProductKey = MultiArgs(om.id, vendor)

            try:
                installDate = DateTime(softwareDict['InstallDate'])
                om.setInstallDate = '{0} 00:00:00'.format(installDate.Date())
            except (SyntaxError, TimeError):
                # Date is unreadable or empty, ok to leave blank
                pass
            rm.append(om)

        return rm

    @staticmethod
    def eliminate_underscores(val):
        """Eliminates double underscores in object ID"""
        return val.replace('__', '')
