# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import inspect


# pylint: disable=no-member

def get_func_name(func):
    return func.__name__


def itervalues(dict_like):
    return dict_like.values()


def iteritems(dict_like):
    return dict_like.items()


def getargspec(*args, **kwargs):
    return inspect.getfullargspec(*args, **kwargs)
