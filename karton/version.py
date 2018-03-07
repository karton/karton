# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from __future__ import print_function


__version__ = '1.0.0'

#pylint: disable=invalid-name
numeric_version = tuple(int(v) for v in __version__.split('.'))

if __name__ == '__main__':
    print(__version__)
