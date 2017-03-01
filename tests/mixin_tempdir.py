# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import shutil
import tempfile
import unittest

from karton import (
    pathutils,
    )


class TempDirMixin(unittest.TestCase):
    '''
    Mixin taking care of having a temporary directory for various files which is
    cleaned in `tearDown`.
    '''

    def setUp(self):
        super(TempDirMixin, self).setUp()

        # The realpath is needed on OS X as Docker gets confused on whether the directory can be
        # shared if there are symlinks in it. See <https://github.com/docker/for-mac/issues/1298>.
        self.tmp_dir = os.path.realpath(tempfile.mkdtemp())

    def tearDown(self):
        super(TempDirMixin, self).tearDown()

        shutil.rmtree(self.tmp_dir)

    def make_tmp_sub_dir(self, intermediate=None):
        '''
        Create a directory inside this test's temporary directory.

        intermediate:
            If not None, the new directory will be a sub directory of intermediate
            which will be a subdirectory of the tests' temporary directory.
        Return value:
            The path to an existing empty temporary directory.
        '''
        if intermediate is None:
            base_dir = self.tmp_dir
        else:
            base_dir = os.path.join(self.tmp_dir, intermediate)
            pathutils.makedirs(base_dir)

        return tempfile.mkdtemp(dir=base_dir)
