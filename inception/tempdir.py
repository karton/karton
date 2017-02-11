#! /usr/bin/env python
#
# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import shutil
import tempfile


class TempDir(object):

    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs

        self.path = None

    def __enter__(self):
        self.path = tempfile.mkdtemp(*self._args, **self._kwargs)
        return self.path

    def __exit__(self, exception_type, exception_value, traceback):
        assert self.path is not None
        shutil.rmtree(self.path)
        self.path = None
