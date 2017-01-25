# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import getpass
import os
import socket
import tempfile

import configuration
import dockerctl


class HostSystem(object):
    '''
    Various information about the host system.
    '''

    @property
    def username(self):
        '''
        The username (on the host).
        '''
        return getpass.getuser()

    @property
    def user_home(self):
        '''
        The home directory for the current user (on the host).
        '''
        return os.path.expanduser('~')

    @property
    def hostname(self):
        '''
        The hostname of the host.
        '''
        return socket.gethostname()


class Session(object):
    '''
    Tracks various aspects related to the runtime configuration and settings
    for Karton.
    '''

    DEFAULT_CONFIGURATION_PATH = os.path.join(os.path.expanduser('~'), '.karton')

    def __init__(self, data_dir, host_system, config, docker):
        '''
        Initializes a Session object.

        data_dir - the path to a directory where to store working files.
        config - a configuration.GlobalConfig instance.
        docker - a dockerctl.Docker instance.
        '''
        self._data_dir = data_dir
        self._host_system = host_system
        self._config = config
        self._docker = docker

    @staticmethod
    def default_session():
        # FIXME: We should not use a directory in the temp dir and we should take
        # care of dealing with multiple users.
        return Session(
            os.path.join(tempfile.gettempdir(), 'karton'),
            HostSystem(),
            configuration.GlobalConfig(Session.DEFAULT_CONFIGURATION_PATH),
            dockerctl.Docker())

    @property
    def data_dir(self):
        '''
        The path to a directory where to store working files.

        Note that this directory may or may not exist.
        '''
        return self._data_dir

    @property
    def host_system(self):
        '''
        The runtime.HostSystem object for the session.
        '''
        return self._host_system

    @property
    def config(self):
        '''
        The configuration.GlobalConfig object for the session.
        '''
        return self._config

    @property
    def docker(self):
        '''
        The dockerctl.Docker object for the session.
        '''
        return self._docker
