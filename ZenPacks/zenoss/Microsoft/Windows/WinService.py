##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import re
import logging
import string
from Globals import InitializeClass
from AccessControl import ClassSecurityInfo
from Products.ZenModel.WinService import WinService as BaseWinService
from Products.ZenModel.Service import Service

log = logging.getLogger('zen.MicrosoftWindows')


class WinService(BaseWinService):
    '''
    Model class for Windows Service.
    '''

    description = None
    usermonitor = False

    datasource_id = None

    _properties = BaseWinService._properties + (
        {'id': 'description', 'label': 'Description', 'type': 'string'},
        {'id': 'usermonitor', 'label': 'Manually Selected Monitor State',
            'type': 'boolean'},
    )

    security = ClassSecurityInfo()

    def getClassObject(self):
        """
        Return the ServiceClass for this service.
        """
        if hasattr(self, 'serviceclass') and 'serviceclass' in self.getRelationshipNames():
            return self.serviceclass()
        return None

    def getRRDTemplateName(self):
        try:
            if self.getRRDTemplateByName(self.serviceName):
                return self.serviceName
        except TypeError:
            pass
        return 'WinService'

    def getRRDTemplates(self):
        return [self.getRRDTemplateByName(self.getRRDTemplateName())]

    def is_match(self, service_regex):
        # can be actual name of service or a regex
        allowed_chars = set(string.ascii_letters + string.digits + '_-')
        if not set(service_regex) - allowed_chars:
            return service_regex.lower() == self.serviceName.lower()
        try:
            regx = re.compile(service_regex, re.I)
        except re.error as e:
            log.warn(e)
            return False
        if regx.match(self.serviceName):
            return True
        return False

    def getMonitored(self, datasource):
        # match on start mode and include/exclude list of regex/service names
        # exclusion will override an inclusion
        rtn = False
        for startmode in datasource.startmode.split(','):
            if startmode in self.startMode.split(',') and hasattr(datasource, 'in_exclusions'):
                for service in datasource.in_exclusions.split(','):
                    service_regex = service.strip()
                    if service_regex.startswith('+') and self.is_match(service_regex[1:]):
                        rtn = True
                    elif service_regex.startswith('-') and self.is_match(service_regex[1:]):
                        return False
        return rtn

    def monitored(self):
        """detect and set changes to self.monitor and ensure reindexing."""
        to_monitor = self.is_monitored()
        if self.monitor != to_monitor:
            setattr(self, 'monitor', to_monitor)
            self.index_object()
        return getattr(self, 'monitor')

    def is_monitored(self):
        """Return True if this service should be monitored. False otherwise."""
        # 1 - Check to see if the user has manually set monitor status
        if not self.usermonitor:
            datasource = self.getMonitoredDataSource()
            sc = self.getClassObject()
            # 2 - Check what our template says to do.
            if datasource and datasource.enabled and self.getMonitored(datasource):
                return True
            # 3 check the service class
            elif sc:
                valid_start = self.startMode in sc.monitoredStartModes
                # check the inherited zMonitor property
                return valid_start and self.getAqProperty('zMonitor')
            # 4 otherwise just inherit from the base WinService class
            else:
                return BaseWinService.monitored(self)
        else:
            self.datasource_id = None
            # if so, return whatever user has set it to
            return self.monitor
        return False

    def get_monitored_startmodes(self):
        ''' determine the start modes for this services
            giving precedence to manual monitoring, followed
            by local template override, and falling back on
            service class if not defined
        '''
        if self.usermonitor is True:
            return [self.startMode]

        # give priority to template
        datasource = self.get_template_datasource()
        if datasource and self.getMonitored(datasource) and hasattr(datasource, 'startmode'):
            modes = datasource.startmode.split(',')
            if 'None' in modes:
                modes.remove('None')
            if len(modes) > 0:
                return modes

        # fallback to serviceclass
        sc = self.getClassObject()
        if sc:
            return sc.monitoredStartModes
        return []

    def get_winservices_modes(self):
        '''Return data about this service to ServiceDataSource'''
        return {'modes': self.getMonitoredStartModes(),
                'mode': self.startMode,
                'monitor': self.isMonitored(),
                'severity': self.getFailSeverity(),
                'manual': self.usermonitor,
                'alertifnot': self.get_alertifnot(),
                }

    def getMonitoredDataSource(self):
        '''Return datasource for template if it exists'''
        # try to return datasource, setting back to None if fails
        if self.datasource_id:
            datasource = self.get_template_datasource()
            if not datasource:
                self.datasource_id = None
            return datasource
        else:
            template = self.getRRDTemplate()
            if template:
                self.setMonitoredDataSource()
                return self.get_template_datasource()
        return None

    def setMonitoredDataSource(self):
        ''' set the datasource_id parameter if
            a valid datasource can be found
        '''
        def test_datasource(ds):
            '''set self.datasource_id if valid'''
            if hasattr(ds, 'startmode') and ds.enabled and self.getMonitored(ds):
                self.datasource_id = ds.id

        # if not defined, try to define it
        if not self.datasource_id:
            template = self.getRRDTemplate()
            if template:
                # first check DefaultService
                datasource = template.datasources._getOb('DefaultService', None)
                if datasource:
                    test_datasource(datasource)
                # if it's still undefined, check for other datasources
                if not self.datasource_id:
                    for datasource in template.getRRDDataSources():
                        if datasource.id == 'DefaultService':
                            continue
                        test_datasource(datasource)

    def get_alertifnot(self):
        datasource = self.get_template_datasource()
        if datasource:
            return getattr(datasource, 'alertifnot', 'Running')
        return 'Running'

    def get_template_datasource(self):
        """
            Attempt to return the proper template datasource if it exists
        """
        template = self.getRRDTemplate()
        if template and self.datasource_id:
            return template.datasources._getOb(self.datasource_id, None)
        return None

    def getFailSeverity(self):
        """
        Return the severity for this service when it fails.
        """
        datasource = self.get_template_datasource()
        if datasource:
            return datasource.severity
        return self.getAqProperty("zFailSeverity")

    def getFailSeverityString(self):
        """
        Return a string representation of zFailSeverity
        """
        return self.ZenEventManager.severities[self.getFailSeverity()]

    def getMonitoredStartModes(self):
        return self.get_monitored_startmodes()

    security.declareProtected('Manage DMD', 'manage_editService')
    def manage_editService(self, *args, **kwargs):
        """Edit a Service from a web page.
        """
        tmpl = super(WinService, self).manage_editService(
            *args, **kwargs)
        self.index_object()
        return tmpl

InitializeClass(WinService)
