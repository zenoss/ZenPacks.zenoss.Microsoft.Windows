##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import re
import logging
import shlex
import base64
import csv
from itertools import izip
from pprint import pformat
from cStringIO import StringIO
from twisted.internet import reactor, defer, task
from xml.etree import cElementTree as ET
from . import constants as c
from .util import create_etree_request_sender, get_datetime

log = logging.getLogger('zen.winrm')
_MAX_REQUESTS_PER_COMMAND = 9999


class CommandResponse(object):

    def __init__(self, stdout, stderr, exit_code):
        self._stdout = stdout
        self._stderr = stderr
        self._exit_code = exit_code

    @property
    def stdout(self):
        return self._stdout

    @property
    def stderr(self):
        return self._stderr

    @property
    def exit_code(self):
        return self._exit_code

    def __repr__(self):
        return pformat(dict(
            stdout=self.stdout, stderr=self.stderr, exit_code=self.exit_code))


def _build_command_line_elem(command_line):
    command_line_parts = shlex.split(command_line, posix=False)
    prefix = "rsp"
    ET.register_namespace(prefix, c.XML_NS_MSRSP)
    command_line_elem = ET.Element('{%s}CommandLine' % c.XML_NS_MSRSP)
    command_elem = ET.Element('{%s}Command' % c.XML_NS_MSRSP)
    command_elem.text = command_line_parts[0]
    command_line_elem.append(command_elem)
    for arguments_text in command_line_parts[1:]:
        arguments_elem = ET.Element('{%s}Arguments' % c.XML_NS_MSRSP)
        arguments_elem.text = arguments_text
        command_line_elem.append(arguments_elem)
    tree = ET.ElementTree(command_line_elem)
    str_io = StringIO()
    tree.write(str_io)
    return str_io.getvalue()


def _stripped_lines(stream_parts):
    results = []
    for line in ''.join(stream_parts).splitlines():
        if line.strip():
            results.append(line.strip())
    return results


def _find_shell_id(elem):
    xpath = './/{%s}Selector[@Name="ShellId"]' % c.XML_NS_WS_MAN
    return elem.findtext(xpath).strip()


def _find_command_id(elem):
    xpath = './/{%s}CommandId' % c.XML_NS_MSRSP
    return elem.findtext(xpath).strip()


def _find_stream(elem, command_id, stream_name):
    xpath = './/{%s}Stream[@Name="%s"][@CommandId="%s"]' \
        % (c.XML_NS_MSRSP, stream_name, command_id)
    for elem in elem.findall(xpath):
        if elem.text is not None:
            yield base64.decodestring(elem.text)


def _find_exit_code(elem, command_id):
    command_state_xpath = './/{%s}CommandState[@CommandId="%s"]' \
        % (c.XML_NS_MSRSP, command_id)
    command_state_elem = elem.find(command_state_xpath)
    if command_state_elem is not None:
        exit_code_xpath = './/{%s}ExitCode' % c.XML_NS_MSRSP
        exit_code_text = command_state_elem.findtext(exit_code_xpath)
        return None if exit_code_text is None else int(exit_code_text)


class SingleShotCommand(object):

    def __init__(self, sender):
        self._sender = sender

    @defer.inlineCallbacks
    def run_command(self, command_line):
        """
        Run commands in a remote shell like the winrs application on Windows.
        Accepts multiple commands. Returns a dictionary with the following
        structure:
            CommandResponse
                .stdout = [<non-empty, stripped line>, ...]
                .stderr = [<non-empty, stripped line>, ...]
                .exit_code = <int>
        """
        shell_id = yield self._create_shell()
        cmd_response = yield self._run_command(shell_id, command_line)
        yield self._delete_shell(shell_id)
        defer.returnValue(cmd_response)

    @defer.inlineCallbacks
    def _create_shell(self):
        elem = yield self._sender.send_request('create')
        defer.returnValue(_find_shell_id(elem))

    @defer.inlineCallbacks
    def _run_command(self, shell_id, command_line):
        command_line_elem = _build_command_line_elem(command_line)
        command_elem = yield self._sender.send_request(
            'command', shell_id=shell_id, command_line_elem=command_line_elem)
        command_id = _find_command_id(command_elem)
        stdout_parts = []
        stderr_parts = []
        for i in xrange(_MAX_REQUESTS_PER_COMMAND):
            receive_elem = yield self._sender.send_request(
                'receive', shell_id=shell_id, command_id=command_id)
            stdout_parts.extend(
                _find_stream(receive_elem, command_id, 'stdout'))
            stderr_parts.extend(
                _find_stream(receive_elem, command_id, 'stderr'))
            exit_code = _find_exit_code(receive_elem, command_id)
            if exit_code is not None:
                break
        else:
            raise Exception("Reached max requests per command.")
        yield self._sender.send_request(
            'signal',
            shell_id=shell_id,
            command_id=command_id,
            signal_code=c.SHELL_SIGNAL_TERMINATE)
        stdout = _stripped_lines(stdout_parts)
        stderr = _stripped_lines(stderr_parts)
        defer.returnValue(CommandResponse(stdout, stderr, exit_code))

    @defer.inlineCallbacks
    def _delete_shell(self, shell_id):
        yield self._sender.send_request('delete', shell_id=shell_id)


def create_single_shot_command(conn_info):
    sender = create_etree_request_sender(conn_info)
    return SingleShotCommand(sender)


class LongRunningCommand(object):

    def __init__(self, sender):
        self._sender = sender
        self._shell_id = None
        self._command_id = None
        self._exit_code = None

    @defer.inlineCallbacks
    def start(self, command_line):
        log.debug("LongRunningCommand run_command: {0}".format(command_line))
        elem = yield self._sender.send_request('create')
        self._shell_id = _find_shell_id(elem)
        command_line_elem = _build_command_line_elem(command_line)
        log.debug('LongRunningCommand run_command: sending command request '
                  '(shell_id={0}, command_line_elem={1})'.format(
                  self._shell_id, command_line_elem))
        command_elem = yield self._sender.send_request(
            'command', shell_id=self._shell_id,
            command_line_elem=command_line_elem)
        self._command_id = _find_command_id(command_elem)

    @defer.inlineCallbacks
    def receive(self):
        receive_elem = yield self._sender.send_request(
            'receive',
            shell_id=self._shell_id,
            command_id=self._command_id)
        stdout_parts = _find_stream(receive_elem, self._command_id, 'stdout')
        stderr_parts = _find_stream(receive_elem, self._command_id, 'stderr')
        self._exit_code = _find_exit_code(receive_elem, self._command_id)
        stdout = _stripped_lines(stdout_parts)
        stderr = _stripped_lines(stderr_parts)
        defer.returnValue((stdout, stderr))

    @defer.inlineCallbacks
    def stop(self):
        yield self._sender.send_request(
            'signal',
            shell_id=self._shell_id,
            command_id=self._command_id,
            signal_code=c.SHELL_SIGNAL_CTRL_C)
        stdout, stderr = yield self.receive()
        yield self._sender.send_request(
            'signal',
            shell_id=self._shell_id,
            command_id=self._command_id,
            signal_code=c.SHELL_SIGNAL_TERMINATE)
        yield self._sender.send_request('delete', shell_id=self._shell_id)
        defer.returnValue(CommandResponse(stdout, stderr, self._exit_code))


def create_long_running_command(conn_info):
    sender = create_etree_request_sender(conn_info)
    return LongRunningCommand(sender)


class Typeperf(object):

    def __init__(self, long_running_command):
        self._long_running_command = long_running_command
        self._counters = None
        self._row_count = 0

    @defer.inlineCallbacks
    def start(self, counters, time_between_samples=1):
        self._counters = counters
        self._row_count = 0
        quoted_counters = ['"{0}"'.format(c) for c in counters]
        command_line = 'typeperf {0} -si {1}'.format(
            ' '.join(quoted_counters), time_between_samples)
        yield self._long_running_command.start(command_line)

    @defer.inlineCallbacks
    def receive(self):
        """
        Returns a pair, (<dictionary>, <stripped stderr lines>), where the
        dictionary is {<counter>: [(<datetime>, <float>)]}"""
        stdout, stderr = yield self._long_running_command.receive()
        dct = {}
        for counter in self._counters:
            dct[counter] = []
        for row in csv.reader(stdout):
            self._row_count += 1
            if self._row_count == 1:
                continue
            try:
                timestamp = get_datetime(row[0])
            except ValueError as e:
                log.debug('Typeperf receive {0}. {1}'.format(row, e))
                continue
            for counter, value in izip(self._counters, row[1:]):
                dct[counter].append((timestamp, float(value)))
        defer.returnValue((dct, stderr))

    @defer.inlineCallbacks
    def stop(self):
        yield self._long_running_command.stop()
        self._counters = None
        self._row_count = 0


def create_typeperf(conn_info):
    long_running_command = create_long_running_command(conn_info)
    return Typeperf(long_running_command)


class RemoteShell(object):

    _PROMPT_PATTERN = re.compile(r'[A-Z]:\\.*>$')
    _READ_DELAY = 0.2

    def __init__(self, sender, include_exit_codes=False):
        self._sender = sender
        self._include_exit_codes = include_exit_codes
        self._reset()

    def __del__(self):
        self.delete()

    @property
    def prompt(self):
        return self._prompt

    @defer.inlineCallbacks
    def create(self):
        if self._shell_id is not None:
            self.delete()
        log.debug("RemoteShell create: sending create request")
        elem = yield self._sender.send_request('create')
        self._shell_id = _find_shell_id(elem)
        command_line_elem = _build_command_line_elem('cmd')
        log.debug('RemoteShell create: sending command request (shell_id={0}, '
                  'command_line_elem={1})'.format(
                  self._shell_id, command_line_elem))
        command_elem = yield self._sender.send_request(
            'command', shell_id=self._shell_id,
            command_line_elem=command_line_elem)
        self._command_id = _find_command_id(command_elem)
        self._deferred_receiving = self._start_receiving()
        stdout = []
        stderr = []
        while self._prompt is None:
            out, err = yield task.deferLater(
                reactor, self._READ_DELAY, self._get_output)
            stderr.extend(err)
            for line in out:
                if self._PROMPT_PATTERN.match(line):
                    self._prompt = line
                else:
                    stdout.append(line)
        defer.returnValue(CommandResponse(stdout, stderr, None))

    @defer.inlineCallbacks
    def run_command(self, command):
        stdout, stderr = yield self._run_command(command)
        if self._include_exit_codes:
            o2, e2 = yield self._run_command('echo %errorlevel%')
            exit_code = o2[0]
        else:
            exit_code = None
        defer.returnValue(CommandResponse(stdout, stderr, exit_code))

    @defer.inlineCallbacks
    def delete(self):
        if self._shell_id is None:
            return
        self.run_command('exit')
        exit_code = yield self._deferred_receiving
        yield self._sender.send_request(
            'signal',
            shell_id=self._shell_id,
            command_id=self._command_id,
            signal_code=c.SHELL_SIGNAL_TERMINATE)
        yield self._sender.send_request('delete', shell_id=self._shell_id)
        stdout, stderr = self._get_output()
        self._reset()
        defer.returnValue(CommandResponse(stdout, stderr, exit_code))

    def _reset(self):
        self._shell_id = None
        self._command_id = None
        self._deferred_receiving = None
        self._prompt = None
        self._stdout_parts = []
        self._stderr_parts = []

    @defer.inlineCallbacks
    def _start_receiving(self):
        exit_code = None
        while exit_code is None:
            receive_elem = yield task.deferLater(
                reactor, self._READ_DELAY, self._sender.send_request,
                'receive', shell_id=self._shell_id,
                command_id=self._command_id)
            self._stdout_parts.extend(
                _find_stream(receive_elem, self._command_id, 'stdout'))
            self._stderr_parts.extend(
                _find_stream(receive_elem, self._command_id, 'stderr'))
            exit_code = _find_exit_code(receive_elem, self._command_id)
        defer.returnValue(exit_code)

    def _get_output(self):
        stdout = _stripped_lines(self._stdout_parts)
        stderr = _stripped_lines(self._stderr_parts)
        del self._stdout_parts[:]
        del self._stderr_parts[:]
        return stdout, stderr

    @defer.inlineCallbacks
    def _run_command(self, command):
        base64_encoded_command = base64.encodestring('{0}\r\n'.format(command))
        yield self._sender.send_request(
            'send',
            shell_id=self._shell_id,
            command_id=self._command_id,
            base64_encoded_command=base64_encoded_command)
        stdout = []
        stderr = []
        for i in xrange(_MAX_REQUESTS_PER_COMMAND):
            out, err = yield task.deferLater(
                reactor, self._READ_DELAY, self._get_output)
            stderr.extend(err)
            if not out:
                continue
            stdout.extend(out[:-1])
            if out[-1] == self._prompt:
                break
            stdout.append(out[-1])
        else:
            raise Exception("Reached max requests per command.")
        defer.returnValue((stdout, stderr))


def create_remote_shell(conn_info, include_exit_codes=False):
    sender = create_etree_request_sender(conn_info)
    return RemoteShell(sender, include_exit_codes)
