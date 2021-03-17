##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging
import re
from zope.interface import implements

from Products.ZenModel.actions import (
    IActionBase, _signalToContextDict, processTalSource)
from Products.ZenModel.interfaces import IAction
from Products.ZenUtils.guid.guid import GUIDManager
from Products.Zuul.interfaces import IInfo
from Products.Zuul.infos import InfoBase
from Products.Zuul.infos.actions import ActionFieldProperty
from Products.Zuul.form import schema
from Products.ZenEvents import ZenEventClasses
from Products.Zuul.utils import ZuulMessageFactory as _t
from ZODB.transact import transact

from .utils import addLocalLibPath
addLocalLibPath()
# Requires addLocalLibPath to be called above.
from txwinrm.collect import ConnectionInfo
from txwinrm.WinRMClient import SingleCommandClient


log = logging.getLogger("zen.actions.WinCommand")


class IWinCommandActionContentInfo(IInfo):
    wincmd_command = schema.Text(
        title=_t(u'Windows CMD Command'),
        description=_t(u'The template for the body for commands.'))
    clear_wincmd_command = schema.Text(
        title=_t(u'Clear Windows CMD Command'),
        description=_t(u'The template for the body for CLEAR commands.'))


class WinCommandActionContentInfo(InfoBase):
    implements(IWinCommandActionContentInfo)

    wincmd_command = ActionFieldProperty(
        IWinCommandActionContentInfo, 'wincmd_command')
    clear_wincmd_command = ActionFieldProperty(
        IWinCommandActionContentInfo, 'clear_wincmd_command')


class WinCommandAction(IActionBase):
    """
    Derived class to execute an arbitrary command on a remote windows machine
    when a notification is triggered.
    """
    implements(IAction)

    id = 'wincommand'
    name = 'WinCommand'
    actionContentInfo = IWinCommandActionContentInfo

    def setupAction(self, dmd):
        """
        Configure the action with properties form the dmd.
        """
        self.guidManager = GUIDManager(dmd)
        self.dmd = dmd

    def updateContent(self, content=None, data=None):
        """
        Update notification content.
        Called when changes are submitted in the 'Edit Notification' form.
        """
        updates = dict()

        for k in ('wincmd_command', 'clear_wincmd_command'):
            updates[k] = data.get(k)

        content.update(updates)

    def execute(self, notification, signal):
        """
        Set up the execution environment and run a CMD command.
        """
        self.setupAction(notification.dmd)
        log.debug('Executing action: {0}'.format(self.name))

        if signal.clear:
            command = notification.content['clear_wincmd_command']
        else:
            command = notification.content['wincmd_command']

        environ = self._get_environ(notification, signal)

        if not command:
            log.debug("The CMD command was not set")
            return

        if not hasattr(environ['dev'], 'windows_servername'):
            log.debug("The target device is non-Windows device")
            return

        try:
            command = processTalSource(command, **environ)
        except Exception:
            log.error('Unable to perform TALES evaluation on "{0}" '
                '-- is there an unescaped $?'.format(command))

        log.debug('Executing this compiled command "{0}"'.format(command))
        self._execute_command(environ['dev'], command)

    def _get_environ(self, notification, signal):
        """
        Set up TALES environment for the action.
        """
        actor = signal.event.occurrence[0].actor
        device = None
        if actor.element_uuid:
            device = self.guidManager.getObject(actor.element_uuid)

        component = None
        if actor.element_sub_uuid:
            component = self.guidManager.getObject(actor.element_sub_uuid)

        environ = dict(dev=device, component=component, dmd=notification.dmd)
        data = _signalToContextDict(signal, self.options.get('zopeurl'),
                                    notification, self.guidManager)
        environ.update(data)
        return environ

    def _conn_info(self, device):
        """
        Return a ConnectionInfo object with device credentials.
        """
        service = device.zWinScheme
        if hasattr(device, 'zWinUseWsmanSPN') and device.zWinUseWsmanSPN:
            service = 'wsman'
        envelope_size = getattr(device, 'zWinRMEnvelopeSize', 512000)
        locale = getattr(device, 'zWinRMLocale', 'en-US')
        code_page = getattr(device, 'zWinRSCodePage', 65001)
        include_dir = getattr(device, 'zWinRMKrb5includedir', None)
        disable_rdns = getattr(device, 'kerberos_rdns', False)
        if callable(disable_rdns):
            disable_rdns = disable_rdns()
        connect_timeout = getattr(device, 'zWinRMConnectTimeout', 60)
        return ConnectionInfo(
            hostname=device.windows_servername() or device.manageIp,
            auth_type='kerberos' if '@' in device.zWinRMUser else 'basic',
            username=device.zWinRMUser,
            password=device.zWinRMPassword,
            scheme=device.zWinScheme,
            port=int(device.zWinRMPort),
            connectiontype='Keep-Alive',
            keytab=device.zWinKeyTabFilePath,
            dcip=device.zWinKDC,
            trusted_realm=device.zWinTrustedRealm,
            trusted_kdc=device.zWinTrustedKDC,
            ipaddress=device.manageIp,
            service=service,
            envelope_size=envelope_size,
            locale=locale,
            code_page=code_page,
            include_dir=include_dir,
            disable_rdns=disable_rdns,
            connect_timeout=connect_timeout)

    def _execute_command(self, device, command):
        """
        Create WinRS client and run the command remotely.
        """
        winrs = SingleCommandClient(self._conn_info(device))
        result = winrs.run_command(str(command))

        result.addCallback(lambda res: self._on_success(device, res, command))
        result.addErrback(lambda err: self._on_error(device, err))

    def _on_success(self, device, result, command):
        """
        Called after the command was successfully executed and
        CommandResponse instance was received.
        """
        if result.exit_code != 0:
            log.error("Command '{0}' failed on host {1}. Reason: {2}".format(
                command, device.manageIp, ' '.join(result.stderr)))
        else:
            log.debug("Command '{0}' was executed on host {1}: {2}".format(
                command, device.manageIp, ' '.join(result.stdout)))

    def _on_error(self, device, error):
        """
        Called if an error occured when connecting to the remote host.
        """
        if hasattr(error, 'value'):
            log.error(error.value)
        else:
            log.error(error)  # Not twisted failure.


@transact
def schedule_remodel(device, evt=None):
    """Schedule the remodeling of device if not already scheduled."""
    if getattr(evt, 'source_uuid', None) and getattr(evt, 'source_event_uuid', None):
        log.debug("Skip scheduling model: Forwarded event")
        return

    if not device:
        log.debug("Skip scheduling model: No device found")
        return

    # Avoid circular import.
    from ZenPacks.zenoss.Microsoft.Windows.Device import Device
    from ZenPacks.zenoss.Microsoft.Windows.ClusterDevice import ClusterDevice

    if not isinstance(device, Device):
        log.debug("Skip scheduling model of %s: Not a Windows device", device.id)
        return

    dmd = device.getDmd()

    if evt:
        eventClassKey = getattr(evt, 'eventClassKey', None)
        if not eventClassKey:
            log.debug(
                "Skip scheduling model of %s: Event with no eventClassKey",
                device.id)

            return

        if eventClassKey not in device.zWindowsRemodelEventClassKeys:
            log.debug(
                "Skip scheduling model of %s: %s not in zWindowsRemodelEventClassKeys",
                device.id, eventClassKey)

            return

        log.info(
            "Scheduling model of %s: %s in zWindowsRemodelEventClassKeys",
            device.id, eventClassKey)

        dmd.ZenEventManager.sendEvent({
            'summary': 'scheduled model caused by event ({})'.format(eventClassKey),
            'cause_evid': evt.evid,
            'device': device.id,
            'component': getattr(evt, 'component', ''),
            'eventClass': ZenEventClasses.Change,
            'severity': ZenEventClasses.Info,
            'monitor': getattr(evt, 'monitor', ''),
            'agent': getattr(evt, 'agent', ''),
        })

    pattern = re.compile(r'zenmodeler .+? %s( |$)' % device.id)
    for job in dmd.JobManager.getUnfinishedJobs():
        if pattern.search(job.job_description):
            log.info('Model of %s already scheduled', device.id)
            return

    log.info('Scheduling model of %s', device.id)
    device.collectDevice(setlog=False, background=True)

    if isinstance(device, ClusterDevice):
        deviceRoot = dmd.getDmdRoot("Devices")
        for host, ip in device.clusterhostdevicesdict.iteritems():
            clusterhost = deviceRoot.findDeviceByIdOrIp(ip)
            if clusterhost:
                clusterhost.collectDevice(setlog=False, background=True)
