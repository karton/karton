# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import errno
import os


def makedirs(dir_path):
    '''
    Create a directory and all the intermediate parent directories.
    '''
    try:
        os.makedirs(dir_path)
    except OSError as exc:
        if exc.errno != errno.EEXIST or not os.path.isdir(dir_path):
            raise


def get_system_executable_paths():
    '''
    Get the directories in $PATH.

    return value - a list of directories.
    '''
    paths = os.environ.get('PATH', '').split(os.pathsep)
    return [path.strip('"').strip('\'') for path in paths if path]
