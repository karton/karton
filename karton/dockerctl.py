# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import proc


class Docker(object):
    '''
    Runs Docker.
    '''

    def __init__(self):
        '''
        Initializes a Docker object.
        '''
        self._docker_command = 'docker'

    def call(self, cmd_args, *args, **kwargs):
        '''
        Like subprocess.call, but the right command for docker is prepended to the
        arguments.
        '''
        return proc.call([self._docker_command] + cmd_args, *args, **kwargs)

    def check_output(self, cmd_args, *args, **kwargs):
        '''
        Like subprocess.check_output, but the right command for docker is prepended
        to the arguments.
        '''
        return proc.check_output([self._docker_command] + cmd_args, *args, **kwargs)
