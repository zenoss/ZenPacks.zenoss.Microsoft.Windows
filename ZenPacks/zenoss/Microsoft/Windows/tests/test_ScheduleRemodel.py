# Platform Imports
from Products.ZenTestCase.BaseTestCase import BaseTestCase
from Products.ZenEvents.Event import Event
from Products.ZenModel.DataRoot import DataRoot
from Products.ZenEvents.MySqlEventManager import MySqlEventManager
from Products.Jobber.manager import JobManager
from Products.ZenRelations.ToOneRelationship import ToOneRelationship
from Products.ZenRelations.ToManyContRelationship import ToManyContRelationship
from Products.ZenModel.DeviceClass import DeviceClass


# ZenPack Imports
from ZenPacks.zenoss.Microsoft.Windows.tests.mock import patch, MagicMock
from ZenPacks.zenoss.Microsoft.Windows.ClusterDevice import ClusterDevice
from ZenPacks.zenoss.Microsoft.Windows.ClusterService import ClusterService
from ZenPacks.zenoss.Microsoft.Windows.actions import schedule_remodel
from ZenPacks.zenoss.DistributedCollector.DistributedPerformanceConf import DistributedPerformanceConf

import Acquisition._Acquisition
import imp

class TestScheduleRemodel(BaseTestCase):

    def setUp(self):
        #set DMD
        ev_manager = MySqlEventManager("manager_id")
        self.job_manager = JobManager("job_id")
        deviceClass = DeviceClass('Devices')

        self.dmd = DataRoot("dmd")
        setattr(self.dmd, 'Devices',deviceClass)
        setattr(self.dmd, 'ZenEventManager',ev_manager)
        setattr(self.dmd, 'JobManager',self.job_manager)

         #set Service
        service1 = ClusterService("cluster-id-123")
        setattr(service1, 'title',"TestAG1")

        service2 = ClusterService("cluster-id-123-456")
        setattr(service2, 'title',"SQL")

        #set Device
        performance = DistributedPerformanceConf("localhost")
        relation = ToOneRelationship("relation_id")
        services = ToManyContRelationship("services_list_id")
        services._add(service1)
        services._add(service2)
        setattr(relation, 'obj',performance)

        self.device = ClusterDevice("/zport/dmd/Devices/Server/Microsoft/Cluster/devices/10.10.10.10")
        setattr(self.device, 'perfServer',relation)
        setattr(self.device, 'zWindowsRemodelEventClassKeys','clusterOwnerChange')
        setattr(self.device, 'clusterhostdevicesdict',dict())
        self.device.os.clusterservices._add(service1)
        self.device.os.clusterservices._add(service2)
        self.device = Acquisition.ImplicitAcquisitionWrapper(self.device, None)
        
        #set Event
        self.event = Event()
        setattr(self.event, 'eventClassKey','clusterOwnerChange')
        setattr(self.event, 'evid','id1234')
        setattr(self.event, 'agent','zenpython')
        setattr(self.event, 'monitor','localhost')
        setattr(self.event, 'device', self.device.id)
     
        self.event2 = Event()
        setattr(self.event2, 'eventClassKey','clusterOwnerChange')
        setattr(self.event2, 'evid','id1234567')
        setattr(self.event2, 'agent','zenpython')
        setattr(self.event2, 'monitor','localhost')
        setattr(self.event2, 'device', self.device.id)

    def set_component_event(self, event, component):
        setattr(event, 'component', component.id)
        message = "OwnerNode of cluster for cluster service {} changed to {}".format(component.title, component.ownernode)
        setattr(event, 'message', message)

    
    def mock_fill_jobs_queue(self,device_ip,queue_size):
        """
        Generator for mocking schedule jobs on the queue
        """        
        for i in range(queue_size):
            description =('Run zenmodeler /opt/zenoss/bin/zminion'
                        ' -minion-name zminion_localhost run -- '
                        '/opt/zenoss/bin/zenmodeler run --now -d '
                        '"/zport/dmd/Devices/Server/Microsoft/Cluster/devices/{}"'
                        ' --monitor localhost --collect=').format(device_ip)
            job = MagicMock(job_description = description , job_id = "job-id-"+str(i)) 
            yield job

    @patch('Products.ZenModel.Device.Device.collectDevice')
    @patch('Products.Jobber.manager.JobManager.getUnfinishedJobs')
    def test_job_already_scheduled_return_zero_calls(self,mock_jobs,collect_mocked):
        """
        Skip remodeling if job is already in the queue
        """
        service = self.device.os.clusterservices.objectItems()[0][1]
        setattr(service,"ownernode","wsc-node-01" )
        self.set_component_event(self.event, service)
        mock_jobs.return_value = self.mock_fill_jobs_queue("10.10.10.10",3)
        schedule_remodel(self.device.__of__(self.dmd), self.event)
        self.assertEquals(collect_mocked.call_count,0)

    @patch('Products.ZenModel.Device.Device.collectDevice')
    @patch('Products.Jobber.manager.JobManager.getUnfinishedJobs')
    def test_job_exit_queue_reattempt_return_one_call(self,mock_jobs,collect_mocked):
        """
        Mocking reschedule called more than once 
        """
        service = self.device.os.clusterservices.objectItems()[0][1]
        setattr(service,"ownernode","wsc-node-03" )
        self.set_component_event(self.event, service)
        mock_jobs.return_value = self.mock_fill_jobs_queue("10.10.10.25",3)
        schedule_remodel(self.device.__of__(self.dmd), self.event)
        schedule_remodel(self.device.__of__(self.dmd), self.event)
        collect_mocked.assert_called_once()
     
    @patch('Products.ZenModel.Device.Device.collectDevice')
    @patch('Products.Jobber.manager.JobManager.getUnfinishedJobs')
    def test_job_not_scheduled_return_one_call(self,mock_jobs,collect_mocked):
        """
        Schedule the job once
        """
        service = self.device.os.clusterservices.objectItems()[1][1]
        setattr(service,"ownernode","wsc-node-02")
        self.set_component_event(self.event, service)
        mock_jobs.return_value = self.mock_fill_jobs_queue("10.10.10.25",3)
        schedule_remodel(self.device.__of__(self.dmd), self.event2)
        collect_mocked.assert_called_once()

    @patch('Products.ZenModel.Device.Device.collectDevice')
    @patch('Products.Jobber.manager.JobManager.getUnfinishedJobs')
    def test_schedule_different_jobs(self,mock_jobs,collect_mocked):
        """
        Schedule each job once
        """
        service =self.device.os.clusterservices.objectItems()[0][1]
        service_2 = self.device.os.clusterservices.objectItems()[1][1]
        setattr(service,"ownernode","wsc-node-02" )
        setattr(service_2,"ownernode","wsc-node-03" )
        self.set_component_event(self.event, service)
        self.set_component_event(self.event, service_2)
        mock_jobs.return_value = self.mock_fill_jobs_queue("10.10.10.25",3)
        schedule_remodel(self.device.__of__(self.dmd), self.event)
        schedule_remodel(self.device.__of__(self.dmd), self.event2)
        self.assertEquals(collect_mocked.call_count,2)


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestScheduleRemodel))
    return suite

