# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import inspect


def get_func_name(func):
    return func.func_name


def itervalues(dict_like):
    return dict_like.itervalues()


def iteritems(dict_like):
    return dict_like.iteritems()


def getargspec(*args, **kwargs):
    return inspect.getargspec(*args, **kwargs)
