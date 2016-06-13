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

from Products.ZenModel.OSComponent import OSComponent
from Products.ZenRelations.RelSchema import ToOne, ToManyCont

log = logging.getLogger('zen.MicrosoftWindows')


class WinService(OSComponent):
    '''
    Model class for Windows Service.
    '''
    meta_type = portal_type = 'WinRMService'


    #startmode [string] = The start mode for the servicename
    #account [string] = The account name the service runs as
    #usermonitor [boolean] = Did user manually set monitor.

    servicename = None
    caption = None
    description = None
    startmode = ''
    account = None
    monitor = False
    usermonitor = False

    _properties = OSComponent._properties + (
        {'id': 'servicename', 'label': 'Service Name', 'type': 'string'},
        {'id': 'caption', 'label': 'Caption', 'type': 'string'},
        {'id': 'description', 'label': 'Description', 'type': 'string'},
        {'id': 'startmode', 'label': 'Start Mode', 'type': 'string'},
        {'id': 'account', 'label': 'Account', 'type': 'string'},
        {'id': 'usermonitor', 'label': 'User Selected Monitor State',
            'type': 'boolean'},
        )

    _relations = OSComponent._relations + (
        ("os", ToOne(ToManyCont,
         "ZenPacks.zenoss.Microsoft.Windows.OperatingSystem",
                     "winrmservices")),
    )

    def getRRDTemplateName(self):
        try:
            if self.getRRDTemplateByName(self.servicename):
                return self.servicename
        except TypeError:
            pass
        return 'WinService'

    def is_match(self, service_regex):
        # can be actual name of service or a regex
        allowed_chars = set(string.ascii_letters + string.digits + '_-')
        if not set(service_regex) - allowed_chars:
            return service_regex == self.servicename
        try:
            regx = re.compile(service_regex)
        except re.error as e:
            log.warn(e)
            return False
        if regx.match(self.servicename):
            return True
        return False

    def getMonitored(self, datasource):
        # match on start mode and include/exclude list of regex/service names
        # exclusion will override an inclusion
        rtn = False
        for startmode in datasource.startmode.split(','):
            if startmode in self.startmode.split(',') and hasattr(datasource, 'in_exclusions'):
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

        return False

InitializeClass(WinService)
