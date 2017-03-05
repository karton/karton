# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import sys

# pylint: disable=wildcard-import,unused-wildcard-import

if sys.version_info[0] >= 3:
    from .compat3 import *
elif sys.version_info[:2] == (2, 7):
    from .compat2 import *
else:
    sys.stderr.write('Python version %d.%d is not supported.\n'
                     'Karton requires Python 2.7 or a version of Python 3.' %
                     sys.version_info[:2])
    sys.exit(1)
