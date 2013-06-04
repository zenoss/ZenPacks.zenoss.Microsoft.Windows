QA Instructions
===============

Installing Zenoss Core and RM
-----------------------------

We need to test against Zenoss RM 4.1.1 and 4.2.3 with recommend patch sets
(RPS) applied.

Use a CentOS 6 machine. It is highly unlikely that we will have a defect
specific to Linux distro / version.

An easy way to install is to use vagrant and VirtualBox. Information is at
http://vagrant.zenoss.loc. Before running 'vagrant up' one of the following 
Vagrantfiles in the current directory, download the box file once and use the
local copy many times with the following commands:

Core 4.2.3

    $ wget http://vagrant.zenoss.loc/boxes/zen-cent6-Core-4.2.3.box
    $ vagrant box add zen-cent6-Core-4.2.3 zen-cent6-Core-4.2.3.box

Vagrantfile

    Vagrant::Config.run do |config|
      config.vm.box = "zen-cent6-Core-4.2.3"
      config.vm.network :bridged
    end

RM 4.2.3

    $ wget http://vagrant.zenoss.loc/boxes/zen-cent6-RM-4.2.3.box
    $ wget box add zen-cent6-RM-4.2.3 zen-cent6-RM-4.2.3.box

Vagrantfile

    Vagrant::Config.run do |config|
      config.vm.box = "zen-cent6-RM-4.2.3"
      config.vm.network :bridged
    end

There is no vagrant box for RM 4.1.1. You could use the cent6 base box and
install the 4.1.1 RPM from artifacts on top of it. The 4.1.1 RPM is available
at http://artifacts.zenoss.loc/releases/4.1.1/ga/resmgr/

You should apply the Recommended Patch Set on top of RM 4.1.1 and 4.2.3. You
should use 4.2.4 instead of 4.2.3 once it comes out. Information on applying
the RPS is at...

* RM 4.1.1 - https://intranet.zenoss.com/docs/DOC-4619
* RM 4.2.3 - https://docs.google.com/a/zenossinc.com/document/d/11jq1zRkJY5Cql4nvVAtzl3qtLHQqHaKo_KdgFRlmeoQ/edit?usp=sharing

If for some reason the 4.2.x vagrant boxes don't work for you, then you can get
the RPMs on artifacts.

* Core 4.2.3 RPM - http://artifacts.zenoss.loc/releases/4.2.3/ga/zenoss_core/
* RM 4.2.3 RPM - http://artifacts.zenoss.loc/releases/4.2.3/ga/resmgr/

Old and New Windows ZenPacks
----------------------------

During testing you will be comparing the behavior of the old Windows ZenPacks
to that of the new one.

Old Windows ZenPacks:

* PySamba
* WindowsMonitor
* ActiveDirectory
* IISMonitor
* MSExchange
* MSMQMonitor
* MSSQLServer

New Windows ZenPacks:

* PythonCollector
* Microsoft.Windows

The old ZenPacks come as part of the Zenoss Core 4.2.x RPM. They can be
installed on top of an RM install with the msmonitor RPM which is available at
http://artifacts.zenoss.loc/releases/4.2.3/ga/msmonitor/

For the new Windows zenpack you can install PythonCollector from 
http://wiki.zenoss.org/ZenPack:PythonCollector

You can use git to fetch the latest stable version of the new Microsoft.Windows
ZenPack from github.

Install git if it is not already installed.

    $ sudo yum -y install git

Download the repo

    $ git clone https://github.com/zenoss/ZenPacks.zenoss.Microsoft.Windows.git

Download the txwinrm repo

    $ cd ZenPacks.zenoss.Microsoft.Windows/src
    $ git clone https://github.com/zenoss/txwinrm.git

Install the zenpack

    $ cd ..
    $ zenpack --link --install .

Set up two machines running Zenoss for each version being tested. One machine
will run the old Windows zenpacks. The second machine will run the new Windows
ZenPack. This will allow you to compare the results of modeling, the graphs,
and events for both the old and new ZPs.

Both ZenPacks on one Zenoss Instance
------------------------------------

Another Test scenario is having both old and new ZenPacks running on same
Zenoss instance. You won't be able to monitor the same device with both because
the system does not allow for duplicate management IP addresses without the
MultiRealmIP ZenPack installed. You will be able to test that various devices
can be monitored and modeled with both ZenPacks and a device can be moved from
the device class of one ZenPack to the other.
