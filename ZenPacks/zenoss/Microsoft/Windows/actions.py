##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import logging

from zope.interface import implements

from Products.ZenModel.actions import (
    IActionBase, _signalToContextDict, processTalSource)
from Products.ZenModel.interfaces import IAction
from Products.ZenUtils.guid.guid import GUIDManager
from Products.Zuul.interfaces import IInfo
from Products.Zuul.infos import InfoBase
from Products.Zuul.infos.actions import ActionFieldProperty
from Products.Zuul.form import schema
from Products.Zuul.utils import ZuulMessageFactory as _t

from .utils import addLocalLibPath
addLocalLibPath()
# Requires addLocalLibPath to be called above.
from txwinrm.collect import ConnectionInfo
from txwinrm.shell import create_single_shot_command


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
            ipaddress=device.manageIp)

    def _execute_command(self, device, command):
        """
        Create WinRS client and run the command remotely.
        """
        winrs = create_single_shot_command(self._conn_info(device))
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
