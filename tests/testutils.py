# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import sys
import tempfile


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
