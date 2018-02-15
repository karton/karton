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
        die('%s DIRECTORY sync|nosync COMMAND [COMMAND-ARGUMENTS]\n'
            '\n'
            'Invalid command line. This command requires at least three arguments.' %
            sys.argv[0])

    container_dir = sys.argv[1]
    do_sync = sys.argv[2]
    actual_args = sys.argv[3:]

    try:
        os.chdir(container_dir)
    except OSError:
        die('Cannot change directory to "%s".\n'
            'It is possible that the image lost its mounts (yeah I know...). '
            'Try to use the "stop" command and rerun this command.' % container_dir)

    # Docker on OS X has clock syncing problems, so we fix it periodically from the host.
    if do_sync == 'sync':
        try:
            # Python 2 doesn't have subprocess.DEVNULL.
            devnull_file = open(os.devnull, 'w')
            subprocess.Popen(
                ['sudo', 'hwclock', '-s'],
                stdout=devnull_file,
                stderr=subprocess.STDOUT)
        except OSError as exc:
            die('Cannot execute the command to set the time: %s' % exc)
        except subprocess.CalledProcessError as exc:
            die('The command to set the time failed: %s' % exc)

    try:
        ret = subprocess.call(actual_args, preexec_fn=dont_ignore_sigint)
    except OSError:
        die('Cannot execute "%s".' % actual_args[0])

    raise SystemExit(ret)


if __name__ == '__main__':
    main(sys.argv)
