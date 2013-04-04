##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

hosts = dict(
    gilroy=('Administrator', 'Z3n0ss'),
    cupertino=('Administrator', 'Z3n0ss'),
    campbell=('Administrator', 'Z3n0ss')
)

wqls = [

    # ZenPacks.zenoss.WindowsMonitor modeler plugins
    # FileSystemMap
    'select * from Win32_logicaldisk',
    'select * from Win32_Volume',


    # WindowsDeviceMap
    'select * from Win32_OperatingSystem',
    'select * from Win32_SystemEnclosure',
    'select * from Win32_ComputerSystem',


    # MemoryMap
    'Select TotalVisibleMemorySize,TotalVirtualMemorySize From '
    'Win32_OperatingSystem',


    # WinServiceMap
    'Select name,caption,pathName,serviceType,startMode,startName,state '
    'From Win32_Service',


    # IpRouteMap
    'Select destination,interfaceindex,mask,metric1,metric2,metric3,'
    'metric4,metric5,nexthop,protocol,type From Win32_IP4RouteTable',


    # IpInterfaceMap
    'Select * From Win32_NetworkAdapterConfiguration',

    'Select * From Win32_PerfRawData_Tcpip_NetworkInterface',


    # CpuMap
    'Select deviceid,InstalledSize From Win32_CacheMemory',

    'Select deviceid,description,manufacturer,socketdesignation,'
    'currentclockspeed,extclock,currentvoltage,l2cachesize,version From '
    'Win32_Processor',


    # ProcessMap
    'Select * From Win32_Process',


    # zenwin
    'SELECT Name, State, StartMode FROM Win32_Service',


    # Performance Data
    # \Disk Read Bytes/sec
    'select name,DiskReadBytesPerSec from '
    'Win32_PerfRawData_PerfDisk_PhysicalDisk',

    'select * from Win32_PerfRawData_PerfProc_Process',


    # # SoftwareMap
    # # In Windows 2003 Server, Win32_Product is not enabled by default, and
    # # must be enabled as follows:
    # #   1. In Add or Remove Programs, click Add/Remove Windows Components.
    # #   2. In the Windows Components Wizard, select Management and Monitoring
    # #      Tools and then click Details.
    # #   3. In the Management and Monitoring Tools dialog box, select WMI
    # #      Windows Installer Provider and then click OK.
    # #   4. Click Next.
    # # 'Select name,installdate from Win32_Product',


    # ZenPacks.zenoss.MSMQMonitor modeler plugins
    # MSMQQueueMap
    # 'Select name From Win32_PerfFormattedData_MSMQ_MSMQQueue',

]
