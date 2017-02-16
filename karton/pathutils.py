# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import errno
import os
import shutil

from .log import verbose


def makedirs(dir_path):
    '''
    Create a directory and all the intermediate parent directories.

    This behavers like `os.makedirs` but doesn't raise an exception if the
    directory already exists.
    '''
    try:
        os.makedirs(dir_path)
    except OSError as exc:
        if exc.errno != errno.EEXIST or not os.path.isdir(dir_path):
            raise


def copy_path(src, dst):
    '''
    Copy file or directory `src` to `dst`.

    This is equivalent to `shutil.copyfile` if `src` is a file or `shutil.copytree` if
    `dst` is a directory.

    src:
        The source file or directory.
    dst:
        The destination.
    '''
    try:
        shutil.copyfile(src, dst)
    except OSError as exc:
        if exc.errno == errno.EISDIR:
            shutil.copytree(src, dst)
        else:
            raise


def hard_link_or_copy(src, dst):
    '''
    Create a hard link from `src` to `dst` if possible. Otherwise copy `src` to `dst`.

    src:
        The source file or directory.
    dst:
        The destination.
    '''
    try:
        os.link(src, dst)
    except OSError as exc:
        if exc.errno in (errno.EXDEV, errno.EPERM):
            # Cannot create the hard link, maybe src is a directory or src and dst are on
            # different devices, so we cannot link.
            verbose('Failed to link from "%s" to "%s" as they are not different devices. '
                    'Copying instead.' %
                    (src, dst))
            copy_path(src, dst)
        else:
            raise


def get_system_executable_paths():
    '''
    Get the directories in the `$PATH` environment variable.

    Return value:
        A list of directories.
    '''
    paths = os.environ.get('PATH', '').split(os.pathsep)
    return [path.strip('"').strip('\'') for path in paths if path]
