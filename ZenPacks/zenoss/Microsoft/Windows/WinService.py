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

log = logging.getLogger('zen.MicrosoftWindows')


class WinService(BaseWinService):
    '''
    Model class for Windows Service.
    '''
    meta_type = portal_type = 'WinRMService'

    servicename = None
    caption = None
    description = None
    startmode = ''
    account = None
    monitor = False
    usermonitor = False

    _properties = BaseWinService._properties + (
        {'id': 'servicename', 'label': 'Service Name', 'type': 'string'},
        {'id': 'caption', 'label': 'Caption', 'type': 'string'},
        {'id': 'description', 'label': 'Description', 'type': 'string'},
        {'id': 'startmode', 'label': 'Start Mode', 'type': 'string'},
        {'id': 'account', 'label': 'Account', 'type': 'string'},
        {'id': 'usermonitor', 'label': 'User Selected Monitor State',
            'type': 'boolean'},
    )

    security = ClassSecurityInfo()

    def getClassObject(self):
        """
        Return the ServiceClass for this service.
        """
        return self.serviceClass()

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
            return service_regex == self.serviceName
        try:
            regx = re.compile(service_regex)
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
        """Return True if this service should be monitored. False otherwise."""

        # 1 - Check to see if the user has manually set monitor status
        if self.usermonitor is True:
            return self.monitor

        # 2 - Check what our template says to do.
        template = self.getRRDTemplate()
        if template:
            datasource = template.datasources._getOb('DefaultService', None)
            if datasource:
                if self.getMonitored(datasource):
                    return True
            # 3 - Allow for other datasources to be specified.
            for datasource in template.getRRDDataSources():
                if datasource.id != 'DefaultService' and hasattr(datasource, 'startmode'):
                    if self.getMonitored(datasource):
                        return True

        # 3 check the service class
        if hasattr(self, 'serviceclass') and 'serviceclass' in self.getRelationshipNames():
            sc = self.serviceclass()
            if sc:
                org = sc.serviceorganizer()
                # check the service class monitored start modes
                if self.startMode in sc.monitoredStartModes:
                    # check the zMonitor organizer property
                    if org and hasattr(org, 'zMonitor'):
                        return org.zMonitor
        # don't monitor Disabled services
        if self.startMode and self.startMode == "Disabled":
            return False

        return False

    def get_serviceclass_startmodes(self):
        ''' determine the start modes for this services
            giving precedence to manual monitoring, followed
            by local template override, and falling back on
            service class if not defined
        '''
        if self.usermonitor is True:
            return [self.startMode]

        template = self.getRRDTemplate()
        if template:
            datasource = template.datasources._getOb('DefaultService', None)
            if datasource and self.getMonitored(datasource):
                modes = datasource.startmode.split(',')
                if 'None' in modes:
                    modes.remove('None')
                if len(modes) > 0:
                    return modes
            # 3 - Allow for other datasources to be specified.
            for datasource in template.getRRDDataSources():
                if datasource.id != 'DefaultService' and hasattr(datasource, 'startmode'):
                    if self.getMonitored(datasource):
                        modes = datasource.startmode.split(',')
                        if 'None' in modes:
                            modes.remove('None')
                        if len(modes) > 0:
                            return modes
        sc = self.serviceclass()
        if sc:
            return sc.monitoredStartModes

    def get_winservices_modes(self):
        ''''''
        data = {}
        for svc in self.device().os.winservices():
            if svc.monitored():
                data[svc.id] = {'modes': svc.get_serviceclass_startmodes(),
                                'mode': svc.startMode,
                                'monitor': svc.monitored()
                                }
        return data

    def getMonitoredStartModes(self):
        return self.get_serviceclass_startmodes()

    security.declareProtected('Manage DMD', 'manage_editService')
    def manage_editService(self, *args, **kwargs):
        """Edit a Service from a web page.
        """
        tmpl = super(WinService, self).manage_editService(
            *args, **kwargs)
        self.index_object()
        return tmpl

InitializeClass(WinService)
