# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import sys
import tempfile

from karton import (
    version,
    )


class Redirector(object):
    '''
    Redirect standard output and error to a file. Use with a `with` block.

    The mixed output and error can be accessed through `content`.

    Setting `sys.stdout` and `sys.stderr` doesn't work for spwaned processes.
    When spawning we could pipe the output and error somewhere, but that means changing
    the internals of how Karton launches applications and would lead to a different code
    path when run under tests.

    This class allows all the output and error messages, both from Python itself and from
    spawned processes, to be redirected.
    '''

    def __init__(self):
        self._original_fds = None
        self._old_stdout = None
        self._old_stderr = None
        self._redirected_path = None
        self._redirected_file = None

        self.content = None

    def __enter__(self):
        assert self._original_fds is None, 'You can only use this object once'

        # Save the original FDs and file objects.
        # FIXME: How about stdin?
        self._original_fds = [(fd, os.dup(fd)) for fd in (1, 2)]
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr

        # Redirect the Python file objects.
        throwaway_fileno, self._redirected_path = tempfile.mkstemp()
        # We need to reopen the file or Python and non-Python will have two different
        # positions in the file (and we can't build a file object from a fileno).
        os.close(throwaway_fileno)
        self._redirected_file = open(self._redirected_path, 'w')
        sys.stdout = self._redirected_file
        sys.stderr = self._redirected_file

        # Redirect the standard FDs.
        os.dup2(self._redirected_file.fileno(), 1)
        os.dup2(self._redirected_file.fileno(), 2)

        return self

    def __exit__(self, exception_type, exception_value, traceback):
        # Restore the Python file objects.
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr
        self._redirected_file.close()

        # Restore the standard FDs.
        for standard_fd, duplicated_fd in self._original_fds:
            os.close(standard_fd)
            os.dup2(duplicated_fd, standard_fd)
            os.close(duplicated_fd)

        # Get the output out from the file.
        with open(self._redirected_path) as redirected_file:
            self.content = redirected_file.read()

        # Cleanup.
        os.unlink(self._redirected_path)


class BinPathAdder(object):
    '''
    Add a directory to `$PATH`.

    This is supposed to be used to be used with a `with` block.
    '''

    def __init__(self, additional_dir):
        '''
        Initialize a `BinPathAdder`.

        additional_dir:
            The directory to add to `$PATH`.
        '''
        self.additional_dir = additional_dir

    @property
    def _dir_and_separator(self):
        return self.additional_dir + ':'

    def __enter__(self):
        os.environ['PATH'] = self._dir_and_separator + os.environ['PATH']
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        assert os.environ['PATH'].startswith(self._dir_and_separator)
        os.environ['PATH'] = os.environ['PATH'][len(self._dir_and_separator):]


class WorkDir(object):
    '''
    Temporarily change the current working directory.

    This is supposed to be used to be used with a `with` block. Inside the
    block, the directory is changed, but the previous one is restored when
    the block exits.
    '''

    def __init__(self, new_work_dir):
        '''
        Initialize a `WorkDir`.

        new_work_dir:
        '''
        self._old_work_dir = None
        self._new_work_dir = new_work_dir

    def __enter__(self):
        assert self._old_work_dir is None
        assert self._new_work_dir is not None

        self._old_work_dir = os.getcwd()
        os.chdir(self._new_work_dir)

        return self

    def __exit__(self, exception_type, exception_value, traceback):
        assert self._old_work_dir is not None

        os.chdir(self._old_work_dir)
        self._old_work_dir = None


class OverwriteVersion(object):
    '''
    Temporarily changes Karton's numeric version.

    This is supposed to be used with a `with` block. Inside the version in
    `version.numeric_version` is overwritten, but the previous version is
    restored when the block exits.
    '''

    @staticmethod
    def version_as_text(numeric_version):
        return '.'.join(str(v) for v in numeric_version)

    def __init__(self, numeric_version=(0, 0, 0)):
        '''
        Initialize a `OverwriteVersion`.

        numeric_version:
            The version to temporarily use.
        '''
        self._fake_version = numeric_version

        assert self.version_as_text(version.numeric_version) == version.__version__
        self._real_version = version.numeric_version

    def _set_text_version_from_numeric(self):
        version.__version__ = self.version_as_text(version.numeric_version)

    def __enter__(self):
        version.numeric_version = self._fake_version
        self._set_text_version_from_numeric()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        version.numeric_version = self._real_version
        self._set_text_version_from_numeric()
