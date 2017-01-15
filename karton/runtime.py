# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os

import configuration


class Session(object):
    '''
    Tracks various aspects related to the runtime configuration and settings
    for Karton.
    '''

    DEFAULT_CONFIGURATION_FILE = os.path.join(os.path.expanduser('~'), '.karton.cfg')

    def __init__(self, config):
        '''
        Initializes a Session object.

        config - a configuration.GlobalConfig instance.
        '''
        self._config = config

    @staticmethod
    def default_session():
        return Session(configuration.GlobalConfig(Session.DEFAULT_CONFIGURATION_FILE))

    @property
    def config(self):
        '''
        The configuration.GlobalConfig object for the session.
        '''
        return self._config
