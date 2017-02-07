# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import proc

from log import die, verbose


def die_docker_not_running(output):
    '''
    Docker is not running, so Karton cannot work and needs to abort.

    output:
        The output of a Docker invokation.
    '''
    die('Failed to run docker. Is it running?\nProgram output:\n\n%s' % output)


class Docker(object):
    '''
    Run Docker.
    '''

    def __init__(self):
        '''
        Initialize a Docker object.
        '''
        self._docker_command = 'docker'

    def call(self, cmd_args, *args, **kwargs):
        '''
        Like `subprocess.call`, but the right command for docker is prepended to the
        arguments.
        '''
        return proc.call([self._docker_command] + cmd_args, *args, **kwargs)

    def check_call(self, cmd_args, *args, **kwargs):
        '''
        Like `subprocess.check_call`, but the right command for docker is prepended
        to the arguments.
        '''
        return proc.check_call([self._docker_command] + cmd_args, *args, **kwargs)

    def check_output(self, cmd_args, *args, **kwargs):
        '''
        Like `subprocess.check_output`, but the right command for docker is prepended
        to the arguments.
        '''
        return proc.check_output([self._docker_command] + cmd_args, *args, **kwargs)

    def is_container_running(self, container_id):
        '''
        Whether the container with `container_id` as ID is running or not.

        Note that this method assumes that Docker is running. If not it will call
        `dockerctl.die_docker_not_running`.

        container_id:
            The ID of the container to query for its status.
        Return value:
            `True` if the container is running, `False` otherwise.
        '''
        verbose('Checking whether Docker container with ID <%s> is running.' % container_id)

        try:
            output = self.check_output(
                ['inspect', '--format={{ .State.Running }}', container_id],
                stderr=proc.STDOUT)
        except proc.CalledProcessError:
            verbose('Cannot inspect the status of the Docker container.')

            # Did inspect fail just because docker is not running?
            try:
                self.check_output(['images'], stderr=proc.STDOUT)
            except proc.CalledProcessError as exc:
                die_docker_not_running(exc.output)

            verbose('Docker seems to be running, but we could not inspect the status of the '
                    'container. Assuming the Docker container is not running.')

            return False

        output = output.strip()
        if output == 'true':
            verbose('Docker container running.')
            return True
        else:
            verbose('Docker container not running.')
            return False
