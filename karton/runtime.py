# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import getpass
import os
import socket

from . import (
    configuration,
    dockerctl,
    pathutils,
    )


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
    def uid(self):
        '''
        The uid of the active user.
        '''
        return os.getuid()

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

    @staticmethod
    def configuration_dir():
        '''
        The directory where configuration files are.

        This defaults to "~/.karton/" but can be overwritten with the `$KARTON_CONFIG_DIR`
        environment variable.
        Note that this is a development feature only, e.g. to write tests, so it should
        not be used for general purposes (that's why it's exposed as a static method
        instead of being configurable like all the other options).

        Return value:
            The directory where the configuration files are.
        '''
        env_dir = os.getenv('KARTON_CONFIG_DIR')
        if env_dir:
            return env_dir

        return os.path.join(os.path.expanduser('~'), '.karton')

    def __init__(self, data_dir, host_system, config, docker):
        '''
        Initialize a `Session` instance.

        data_dir:
            The path to a directory where to store working files.
        config:
            A `configuration.GlobalConfig` instance.
        docker:
            A `dockerctl.Docker` instance.
        '''
        self._data_dir = data_dir
        self._host_system = host_system
        self._config = config
        self._docker = docker

    @staticmethod
    def default_session():
        '''
        A `Session` using the default configuration, dirs, etc.
        '''
        # FIXME: We should not use a directory in the temp dir and we should take
        # care of dealing with multiple users.
        return Session(
            os.path.join(pathutils.get_user_runtime_path(), 'io.github.karton'),
            HostSystem(),
            configuration.GlobalConfig(Session.configuration_dir()),
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
        The `runtime.HostSystem` instance for the session.
        '''
        return self._host_system

    @property
    def config(self):
        '''
        The `configuration.GlobalConfig` instance for the session.
        '''
        return self._config

    @property
    def docker(self):
        '''
        The `dockerctl.Docker` instance for the session.
        '''
        return self._docker
