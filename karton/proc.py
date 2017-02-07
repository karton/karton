# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import subprocess

from log import verbose


CalledProcessError = subprocess.CalledProcessError
STDOUT = subprocess.STDOUT


def call(cmd_args, *args, **kwargs):
    '''
    Like `subprocess.call`, but with extra logging in verbose mode.
    '''
    verbose('Calling (using call):\n%s' % cmd_args)
    return subprocess.call(cmd_args, *args, **kwargs)


def check_call(cmd_args, *args, **kwargs):
    '''
    Like `subprocess.check_call`, but with extra logging in verbose mode.
    '''
    verbose('Calling (using check_call):\n%s' % cmd_args)
    return subprocess.check_call(cmd_args, *args, **kwargs)


def check_output(cmd_args, *args, **kwargs):
    '''
    Like `subprocess.check_output`, but with extra logging in verbose mode.
    '''
    verbose('Calling (using check_output):\n%s' % cmd_args)
    return subprocess.check_output(cmd_args, *args, **kwargs)
