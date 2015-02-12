##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Windows Installed Software

Models list of installed software by querying registry.
Querying Win32_Product causes Windows installer to run a consistency check, 
possibly causing other problems to appear.
'''
import re
from DateTime import DateTime
from Products.DataCollector.plugins.DataMaps import MultiArgs

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin


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

    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        rm = self.relMap()
        
        software_results = results.get('software')
        if software_results:
            software_results = ''.join(software_results.stdout).split('|')

        # Registry Software formatting
        if software_results:
            for sw in software_results:
                softwareDict = {}
                try:
                    for keyvalues in sw.split(';'):
                        key, value = keyvalues.split('=')
                        softwareDict[key] = value
     
                    # skip over empty entries
                    if softwareDict['DisplayName'] == '':
                        continue                   
                    om = self.objectMap()
                    om.id = self.eliminate_underscores(self.prepId(softwareDict['DisplayName']))
                    if softwareDict['Vendor'].strip() == '':
                        softwareDict['Vendor'] = 'Unknown'
                        om.Vendor = 'Unknown'

                    om.setProductKey = MultiArgs(softwareDict['DisplayName'], softwareDict['Vendor'])

                    if softwareDict['InstallDate'] is not '':
                        try:
                            installDate = DateTime(softwareDict['InstallDate'])
                            om.setInstallDate = '{0} 00:00:00'.format(installDate.Date())
                        except:
                            # Date is unreadable, leave blank
                            pass
                    rm.append(om)
                    
                except (KeyError, ValueError):
                    pass
                
        return rm

    def eliminate_underscores(self, val):
        """Eliminates double underscores in object ID"""
        return val.replace('__', '')
