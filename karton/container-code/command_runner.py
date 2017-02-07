#! /usr/bin/env python
#
# Copyright (C) 2-16-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from __future__ import print_function

import datetime
import os
import signal
import subprocess
import sys
import time

def error(msg):
    sys.stderr.write(msg)
    sys.stderr.write('\n')


def die(msg):
    error(msg)
    raise SystemExit(1)


def seconds_since_epoch_to_human(seconds):
    return datetime.datetime.fromtimestamp(seconds).strftime('%Y-%m-%d %H:%M:%S')


def dont_ignore_sigint():
    # If we don't do this after forking but before executing the child process,
    # then we don't get SIGINT at all as this script ignores SIGINT.
    signal.signal(signal.SIGINT, signal.SIG_DFL)


def main(args):
    # This script ignores SIGINT. We let the child process handle SIGINT and then
    # we just terminate if it does.
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    if len(sys.argv) < 4:
        die('%s DIRECTORY HOST-TIME COMMAND [COMMAND-ARGUMENTS]\n'
            '\n'
            'Invalid command line. This command requires at least three arguments.' %
            sys.argv[0])

    container_dir = sys.argv[1]
    host_time_string = sys.argv[2]
    actual_args = sys.argv[3:]

    try:
        os.chdir(container_dir)
    except OSError:
        die('Cannot change directory to "%s".\n'
            'It is possible that the image lost its mounts (yeah I know...). '
            'Try to use the "stop" command and rerun this command.' % container_dir)

    try:
        host_time = int(host_time_string)
    except ValueError:
        die('Invalid host time "%s".' % host_time_string)

    container_time = int(time.time())

    # Docker on OS X seems to have clock syncing problems when the host is suspended, so
    # we send the host time (in seconds since the epoch) to the container.
    # We allow some small difference that shouldn't matter, plus a slightly bigger one
    # on one side in case Docker took some time to launch this command.
    if not host_time - 5 <= container_time <= host_time + 25:
        error('The image time is out of sync with the host.')
        error(' - Host time:  ' + seconds_since_epoch_to_human(host_time))
        error(' - Image time: ' + seconds_since_epoch_to_human(container_time))
        error('Updating it.')

        err_msg = \
            '\n' + \
            'Note that, for this to work, the image needs to allow passwordless sudo.\n' + \
            '\n' + \
            'Aborting instead of running commands with the wrong time set.'

        try:
            # FIXME: what if passowrdless sudo is not enabled?
            subprocess.check_call(
                ['sudo', 'date', '-s', '@' + str(host_time)],
                preexec_fn=dont_ignore_sigint)
        except OSError:
            die('Cannot execute the command to set the time.' + err_msg)
        except subprocess.CalledProcessError:
            die('The command to set the time failed.' + err_msg)

    try:
        ret = subprocess.call(actual_args, preexec_fn=dont_ignore_sigint)
    except OSError:
        die('Cannot execute "%s".' % actual_args[0])

    raise SystemExit(ret)


if __name__ == '__main__':
    main(sys.argv)
