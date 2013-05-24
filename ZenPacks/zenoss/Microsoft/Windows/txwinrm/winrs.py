##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import sys
import cmd
from pprint import pprint
from twisted.internet import reactor, defer, task, threads
from . import app
from .shell import create_long_running_command, create_single_shot_command, \
    create_remote_shell


def print_output(stdout, stderr):
    for line in stdout:
        print ' ', line
    for line in stderr:
        print >>sys.stderr, ' ', line


class WinrsCmd(cmd.Cmd):

    def __init__(self, shell):
        cmd.Cmd.__init__(self)
        self._shell = shell
        self.prompt = shell.prompt

    def default(self, line):
        response = threads.blockingCallFromThread(
            reactor, self._run_command, line)
        print '\n'.join(response.stdout)
        print >>sys.stderr, '\n'.join(response.stderr)

    @defer.inlineCallbacks
    def _run_command(self, line):
        response = yield self._shell.run_command(line)
        defer.returnValue(response)

    def do_exit(self, line):
        reactor.callFromThread(self._exit)
        return True

    @defer.inlineCallbacks
    def _exit(self):
        yield self._shell.delete()
        app.stop_reactor()

    def postloop(self):
        print


@defer.inlineCallbacks
def long_running_main(args):
    try:
        client = create_long_running_command(args.conn_info)
        yield client.start(args.command)
        for i in xrange(5):
            stdout, stderr = yield task.deferLater(
                reactor, 1, client.receive)
            print_output(stdout, stderr)
        yield client.stop()
    finally:
        app.stop_reactor()


@defer.inlineCallbacks
def interactive_main(args):
    shell = create_remote_shell(args.conn_info)
    response = yield shell.create()
    intro = '\n'.join(response.stdout)
    winrs_cmd = WinrsCmd(shell)
    reactor.callInThread(winrs_cmd.cmdloop, intro)


@defer.inlineCallbacks
def batch_main(args):
    hostname = args.conn_info.hostname
    command = args.command
    try:
        shell = create_remote_shell(args.conn_info)
        print 'Creating shell on {0}.'.format(hostname)
        yield shell.create()
        for i in range(10):
            print '\nSending to {0}:\n  {1}'.format(hostname, command)
            response = yield shell.run_command(command)
            print '\nReceived from {0}:'.format(hostname)
            print_output(response.stdout, response.stderr)
        response = yield shell.delete()
        print "\nDeleted shell on {0}.".format(hostname)
        print_output(response.stdout, response.stderr)
        print "\nExit code of shell on {0}: {1}".format(
            hostname, response.exit_code)
    finally:
        app.stop_reactor()


@defer.inlineCallbacks
def single_shot_main(args):
    try:
        client = create_single_shot_command(args.conn_info)
        results = yield client.run_command(args.command)
        pprint(results)
    finally:
        app.stop_reactor()


class WinrsUtility(object):

    def tx_main(self, args, config):
        if args.kind == "long":
            long_running_main(args)
        elif args.kind == "single":
            single_shot_main(args)
        elif args.kind == "batch":
            batch_main(args)
        else:
            interactive_main(args)

    def add_args(self, parser):
        parser.add_argument(
            "kind", nargs='?', default="interactive",
            choices=["interactive", "single", "batch", "long"])
        parser.add_argument("--command", "-x")

    def check_args(self, args):
        if not args.command and args.kind in ["single", "batch", "long"]:
            print >>sys.stderr, \
                "ERROR: {0} requires that you specify a command."
            return False
        elif args.config:
            print >>sys.stderr, \
                "ERROR: The winrs command does not support a configuration " \
                "file at this time."
            return False
        return True

    def add_config(self, parser, config):
        pass

    def adapt_args_to_config(self, args, config):
        pass

if __name__ == '__main__':
    app.main(WinrsUtility())
