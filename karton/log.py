# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from __future__ import print_function

import sys


_g_verbose_logging = False


class ExitDueToFailure(SystemExit):
    '''
    Raised by the `die` function to exit the program.
    '''

    def __init__(self, exit_code=1):
        '''
        Initialize an `ExitDueToFailure` instance.

        exit_code:
            The program exit code.
        '''
        super(ExitDueToFailure, self).__init__(exit_code)


def set_verbose(verbose_logging):
    '''
    Set whether to enable verbose logging.

    verbose_logging:
        If true, verbose logging will be enabled; otherwise, it will be disabled.
    '''
    global _g_verbose_logging
    _g_verbose_logging = verbose_logging


def get_verbose():
    '''
    Return whether verbose logging is enabled.

    Return value:
        `True` if verbose logging is enabled; `False` otherwise.
    '''
    return _g_verbose_logging


def die(msg):
    '''
    Print an error message and quit the program
    with an error exit code.

    msg:
        The error message.
    '''
    sys.stderr.write('\n')
    sys.stderr.write(msg)
    sys.stderr.write('\n')
    raise ExitDueToFailure()


def info(msg):
    '''
    Print an informative message.

    msg:
        The message to print.
    '''
    print(msg)


def verbose(msg):
    '''
    Print a message iff verbose logging is enabled.

    msg:
        The message to print.
    '''
    if _g_verbose_logging:
        info(msg)
