# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os


def root_code_dir():
    '''
    The top directory containing the Karton scripts.

    Return value:
        The top directory.
    '''
    return os.path.dirname(os.path.abspath(__file__))
