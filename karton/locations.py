# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import sys


_g_karton_executable = None


def get_karton_executable():
    '''
    The path to the executable script which launches Karton.

    Return value:
        The path to the Karton executable.
    '''
    assert _g_karton_executable is not None
    return _g_karton_executable


def set_karton_executable(executable_path):
    '''
    Set the path to the executable script which launches Karton.

    executable_path:
        The path to the Karton executable.
    '''
    global _g_karton_executable
    _g_karton_executable = os.path.realpath(executable_path)
    if _g_karton_executable.endswith('.pyc') or _g_karton_executable.endswith('.pyo'):
        _g_karton_executable = _g_karton_executable[:-1]


set_karton_executable(sys.argv[0])


def root_code_dir():
    '''
    The top directory containing the Karton scripts.

    Return value:
        The top directory.
    '''
    return os.path.dirname(os.path.abspath(__file__))
