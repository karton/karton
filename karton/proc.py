# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import subprocess

from .log import verbose


CalledProcessError = subprocess.CalledProcessError


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
    Like `subprocess.check_output`, but with extra logging in verbose mode, stderr redirection
    by default and it always returns a string, not bytes.

    The standard error is automatically redirected to standard output (so it's returned
    together with the rest of the output).
    To redirect the standard error somewhere else, specify `stderr=...`.
    To avoid redirecting the standard error output at all, use `stderr=None`.
    '''
    verbose('Calling (using check_output):\n%s' % cmd_args)

    if 'stderr' not in kwargs:
        kwargs['stderr'] = subprocess.STDOUT
    elif kwargs['stderr'] is None:
        del kwargs['stderr']

    if 'universal_newlines' not in kwargs:
        kwargs['universal_newlines'] = True

    # Without universal_newlines, in Python 3, this returns a byte instance.
    return subprocess.check_output(cmd_args, *args, **kwargs)
