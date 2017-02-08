#! /usr/bin/env python
#
# Copyright (C) 2-16-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from __future__ import print_function

import os
import signal


def terminate(signum, stack_frame):
    print('Terminating the image.')
    raise SystemExit(1)


def main():
    pid = os.getpid()
    print('Started with PID %d' % pid)

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, terminate)

    with open('/tmp/karton-session-runner.pid', 'w') as pid_file:
        pid_file.write(str(pid))

    while True:
        signal.pause()
        print('Got a signal, continuing.')


if __name__ == '__main__':
    main()
