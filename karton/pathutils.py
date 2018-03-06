# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import errno
import os
import shutil
import sys
import tempfile

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
    except IOError as exc:
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


def get_user_cache_dir():
    '''
    Get a user-specific directory for non-essential cached files.

    On macOS, this is the per-user temporary directory.

    Return value:
        A directory path which may or may not exist.
    '''
    xdg_cache_dir = os.environ.get('XDG_CACHE_HOME')
    if xdg_cache_dir is not None:
        return xdg_cache_dir

    if sys.platform == 'darwin':
        return tempfile.gettempdir()

    return os.path.expanduser(os.path.join('~', '.cache'))


def get_user_runtime_path():
    '''
    Get a user-specific directory directory for runtime files.

    If not specified according to the XDG Base Directory Specification, then
    the directory returned by `get_user_cache_dir` is used.

    Return value:
        A directory path which may or may not exist.
    '''
    xdg_runtime_dir = os.environ.get('XDG_RUNTIME_DIR')
    if xdg_runtime_dir is not None:
        return xdg_runtime_dir

    return get_user_cache_dir()
