# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from __future__ import print_function

import sys


_g_verbose_logging = False


class ExitDueToFailure(SystemExit):
    '''
    Raised by the die function to exit the program.
    '''

    def __init__(self, exit_code=1):
        '''
        Initializes a ExitDueToFailure object.

        The program exit code can be passed in the exit_code argument.
        '''
        super(ExitDueToFailure, self).__init__(exit_code)


def set_verbose(verbose_logging):
    '''
    Sets whether to enable verbose logging.
    '''
    global _g_verbose_logging
    _g_verbose_logging = verbose_logging


def get_verbose():
    '''
    Returns whether verbose logging is enabled.
    '''
    return _g_verbose_logging


def die(msg):
    '''
    Prints an error message and quits with an error code.
    '''
    sys.stderr.write('\n')
    sys.stderr.write(msg)
    sys.stderr.write('\n')
    raise ExitDueToFailure()


def info(msg):
    '''
    Prints an informative message.
    '''
    print(msg)


def verbose(msg):
    '''
    Prints a message iff verbose logging is enabled.
    '''
    if _g_verbose_logging:
        info(msg)
