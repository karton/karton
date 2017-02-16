# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import errno
import fcntl
import time

from .log import verbose


class TimeoutError(Exception):
    '''
    An error raised when a locking timeout occurs.
    '''
    pass


class FileLock(object):
    '''
    File-based locking.
    '''

    def __init__(self, lock_file_path, timeout=60, timeout_cb=None, still_waiting_cb=None):
        '''
        Initialize a `FileLock` instance.

        lock_file_path:
            The path to the lock file (ideally something in a temporary directory).
        timeout:
            How many seconds to wait before giving up. This is a very rough estimate.
        timeout_cb:
            A function to call if the lock cannot be acquired due to timeout.
            See `acquire` for details.
        still_waiting_cb:
            A function to call once in a while if we are waiting to acquire the lock. This is
            useful, for instance, to print an informative message to the user, so that they
            know the program is not frozen.
        '''
        self._lock_file_path = lock_file_path
        self._timeout = timeout
        self._timeout_cb = timeout_cb
        self._still_waiting_cb = still_waiting_cb

        self._locked = False
        self._lock_file = None
        self._sleep_time = 0.5

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.release()
        return False

    def acquire(self):
        '''
        Acquire the lock.

        This method can take quite a while before returning if the lock is not immediately
        available.

        If a timeout occurs and you passed a timeout callback to the initializer, then this is
        called.

        If no callback was called, or if it was but it didn't raise an exception, then a
        TimeoutError is raised.
        This means that, whatever you do, an exception will be raised. This is important as
        executing code is not safe if this function failed.
        '''
        assert not self._locked
        assert not self._lock_file

        counter = 0

        self._lock_file = open(self._lock_file_path, 'w+')

        while True:
            verbose('Trying to acquire lock "%s", attempt %d' % (self._lock_file_path, counter + 1))
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError as exc:
                if exc.errno != errno.EAGAIN:
                    raise

                time.sleep(self._sleep_time)

                if counter and counter % 5 == 0:
                    if self._still_waiting_cb:
                        self._still_waiting_cb()

                if counter * self._sleep_time >= self._timeout:
                    if self._timeout_cb:
                        self._timeout_cb()
                    raise TimeoutError('Cannot acquire the lock at "%s".' %
                                       self._lock_file_path)

                counter += 1

                continue

            # All done, we have the lock.

            assert not self._locked # This should not have changed!
            self._locked = True

            break

        verbose('Acquired lock "%s"' % self._lock_file_path)

    def release(self):
        '''
        Release a previously acquired lock.
        '''
        assert self._locked
        assert self._lock_file

        # Note that this actually leaves the lock file around, but deleting it without a race
        # is not trivial.
        fcntl.flock(self._lock_file, fcntl.LOCK_UN)
        verbose('Lock "%s" released.' % self._lock_file_path)

        self._locked = False

        self._lock_file.close()
        self._lock_file = None


def _test_self():
    '''
    Manual test for this module.

    Run multiple instances of this script to see locking in action.
    '''
    import os
    import tempfile
    from log import info, set_verbose

    set_verbose(True)

    def timeout_cb():
        info('Oops, we got a timeout!')

    def still_waiting_cb():
        info('Still waiting!')

    with FileLock(os.path.join(tempfile.gettempdir(), 'lock-test'),
                  timeout=20,
                  timeout_cb=timeout_cb,
                  still_waiting_cb=still_waiting_cb):
        info('Starting "with" block')
        time.sleep(15)
        info('Finishing "with" block')


if __name__ == '__main__':
    _test_self()
