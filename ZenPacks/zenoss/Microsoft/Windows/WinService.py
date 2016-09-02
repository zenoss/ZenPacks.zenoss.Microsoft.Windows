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
from Products.ZenEvents import ZenEventClasses

log = logging.getLogger('zen.MicrosoftWindows')

UNMONITORED = 0
MONITORED = 1
EXCLUDED = 2


class WinService(BaseWinService):
    '''
    Model class for Windows Service.
    '''

    description = None
    usermonitor = False

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

    def isMatch(self, service_regex):
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
        # return one of UNMONITORED, MONITORED, EXCLUDED
        monitored = UNMONITORED
        for startmode in datasource.startmode.split(','):
            if startmode in self.startMode.split(',') and hasattr(datasource, 'in_exclusions'):
                for service in datasource.in_exclusions.split(','):
                    service_regex = service.strip()
                    if service_regex.startswith('+') and self.isMatch(service_regex[1:]):
                        monitored = MONITORED
                    elif service_regex.startswith('-') and self.isMatch(service_regex[1:]):
                        return EXCLUDED
        return monitored

    def monitored(self):
        # Determine whether or not to monitor this service
        # Set necessary defaults
        self.alertifnot = 'Running'
        self.failSeverity = ZenEventClasses.Error
        # 1 - Check to see if the user has manually set monitor status
        if self.usermonitor:
            return self.monitor

        # Check what our template says to do.
        template = self.getRRDTemplate()
        if template:
            # 2 - Check DefaultService DataSource
            datasource = template.datasources._getOb('DefaultService', None)
            if datasource and not datasource.enabled and template.id == self.serviceName:
                return False
            if datasource and datasource.enabled:
                status = self.getMonitored(datasource)
                if status is MONITORED:
                    self.failSeverity = datasource.severity
                    self.alertifnot = datasource.alertifnot
                    return True
                elif status is EXCLUDED:
                    return False
            # 3 - Check all other DataSources
            ds_monitored = False
            for datasource in template.getRRDDataSources():
                if datasource.id != 'DefaultService' and\
                   hasattr(datasource, 'startmode') and\
                   datasource.enabled:
                        status = self.getMonitored(datasource)
                        if status is MONITORED:
                            self.failSeverity = datasource.severity
                            self.alertifnot = datasource.alertifnot
                            ds_monitored = True
                        elif status is EXCLUDED:
                            return False
            if ds_monitored:
                return True

        # 4 check the service class
        sc = self.getClassObject()
        if sc:
            valid_start = self.startMode in sc.monitoredStartModes
            # check the inherited zMonitor property
            self.failSeverity = self.getAqProperty("zFailSeverity")

            return valid_start and self.getAqProperty('zMonitor')

        return False

    security.declareProtected('Manage DMD', 'manage_editService')
    def manage_editService(self, *args, **kwargs):
        """Edit a Service from a web page.
        """
        tmpl = super(WinService, self).manage_editService(
            *args, **kwargs)
        self.index_object()
        return tmpl

InitializeClass(WinService)
