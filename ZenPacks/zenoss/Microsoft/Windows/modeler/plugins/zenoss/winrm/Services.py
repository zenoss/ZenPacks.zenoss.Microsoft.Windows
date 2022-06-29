##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, 2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

'''
Windows Services

Models list of installed services by querying Win32_Service via WMI.
'''
import re

from ZenPacks.zenoss.Microsoft.Windows.modeler.WinRMPlugin import WinRMPlugin
from ZenPacks.zenoss.Microsoft.Windows.utils import save
from Products.DataCollector.plugins.DataMaps import RelationshipMap


class Services(WinRMPlugin):
    compname = 'os'
    relname = 'winservices'
    modname = 'ZenPacks.zenoss.Microsoft.Windows.WinService'

    queries = {
        'Win32_Service': "SELECT * FROM Win32_Service",
    }

    @save
    def process(self, device, results, log):
        log.info(
            "Modeler %s processing data for device %s",
            self.name(), device.id)

        model_list, ignore_list, group_list = validate_modeling_regex(device, log)

        rm = self.relMap()

        for service in results.get('Win32_Service', ()):
            if omit_service(model_list, ignore_list, service.Name, log):
                continue
            service_class_name, service_class_caption = truncate_service_class(group_list, service.Name, service.Caption)
            om = self.objectMap()
            om.id = self.prepId(service.Name)
            om.serviceName = service.Name
            om.caption = service.Caption
            om.setServiceClass = {'name': service_class_name, 'description': service_class_caption}
            om.pathName = service.PathName
            om.serviceType = service.ServiceType
            om.startMode = service.StartMode
            om.startName = service.StartName
            om.description = service.Description
            om.index_service = True
            rm.append(om)

        maps = []
        maps.append(RelationshipMap(
            relname="winrmservices",
            compname='os',
            objmaps=[]))
        maps.append(rm)
        return maps


def create_regex_list(device, prop, log):
    result = []
    for name in getattr(device, prop, []):
        try:
            re.compile(name)
            result.append(name)
        except:
            log.warn('Ignoring "{}" in {}. '
                     'Invalid Regular Expression.'.format(name, prop))
    return result


def validate_modeling_regex(device, log):
    model_list = create_regex_list(device, 'zWinServicesModeled', log)
    ignore_list = create_regex_list(device, 'zWinServicesNotModeled', log)
    group_list = create_regex_list(device, 'zWinServicesGroupedByClass', log)
    group_list = [group.strip() for group in group_list if group.strip()]
    return model_list, ignore_list, group_list


def service_in_list(list_, name):
    for value in list_:
        if re.match(value, name):
            return True
    return False


def omit_service(model_list, ignore_list, service_name, log):
    model = service_in_list(model_list, service_name)
    ignore = service_in_list(ignore_list, service_name)

    if ignore:
        return True

    if model_list:
        if model:
            return False
        else:
            return True

    # model all services by default
    return False


def truncate_service_class(group_list, service_name, service_caption):
    service_class_name = service_name
    service_class_caption = service_caption
    if group_list:
        for group in group_list:
            if re.search(group, service_name):
                service_class_name = re.search(group, service_name).group(0)
                matched_caption = re.sub("(?:.(?!_.*))+$", '', service_caption)
                if matched_caption:
                    service_class_caption = matched_caption
                break
    return service_class_name, service_class_caption
