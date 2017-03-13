# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import grp
import json
import os
import pwd
import sys
import textwrap

from . import (
    proc,
    )

from .log import die, verbose


class Docker(object):
    '''
    Run Docker.
    '''

    def __init__(self):
        '''
        Initialize a Docker object.

        docker_command:
            The name of the command to use to invoke Docker.
        '''
        self._docker_command = ['docker']
        self._sudo_command = ['sudo', '-n']
        self._did_check_docker = False

    # Docker could be launched.
    _DOCKER_SUCCESS = 1
    # The command to invoke Docker couldn't be found.
    _DOCKER_NO_COMMAND = 2
    # The Docker server couldn't be contacted.
    _DOCKER_NO_SERVER = 3
    # Another, unexpected, error happened while trying to use a Docker command.
    _DOCKER_OTHER_ERROR = 10

    def _try_docker(self):
        '''
        Try running Docker to check its availability.

        Return value:
            A value indicating where Docker could be run, it wasn't found, the server
            is not available, or an error occurred.
        '''
        version = {}
        json_output = None
        error_return_code = False

        try:
            json_output = proc.check_output(
                self._docker_command + ['version', '--format', '{{ json . }}'],
                stderr=proc.DEVNULL)
        except OSError as exc:
            return self._DOCKER_NO_COMMAND
        except proc.CalledProcessError as exc:
            # The most common case for this is that the server cannot be contacted, so
            # Docker prints out the client version info, but not the server one.
            json_output = exc.output
            error_return_code = True

        assert json_output is not None

        try:
            version = json.loads(json_output)
        except ValueError:
            verbose('The "docker version" command was run, but it didn\'t return valid data.\n'
                    'The output was:\n%s' % json_output)
            return self._DOCKER_OTHER_ERROR

        if version.get('Client') is None:
            verbose('The "docker version" command was run, but it didn\'t return a version?\n'
                    'The output was:\n%s' % json_output)
            return self._DOCKER_OTHER_ERROR
        elif version.get('Server') is None:
            return self._DOCKER_NO_SERVER

        if error_return_code:
            verbose('Inconsistent result from docker.\n'
                    'The docker command failed, but its output doesn\'t report '
                    'any failure.\n'
                    'Ignoring.')

        return self._DOCKER_SUCCESS

    _DOCKER_GROUP_UNAVAILABLE = 1
    _DOCKER_GROUP_DOES_NOT_EXIST = 2
    _DOCKER_GROUP_NOT_IN_GROUP = 3
    _DOCKER_GROUP_CONTAINS_USER = 4

    def _check_docker_group(self):
        if sys.platform == 'darwin':
            return self._DOCKER_GROUP_UNAVAILABLE

        try:
            docker_group = grp.getgrnam('docker')
        except KeyError:
            return self._DOCKER_GROUP_DOES_NOT_EXIST

        current_username = pwd.getpwuid(os.getuid()).pw_name
        if current_username in docker_group.gr_mem:
            return self._DOCKER_GROUP_CONTAINS_USER
        else:
            return self._DOCKER_GROUP_NOT_IN_GROUP

    def _can_use_sudo(self):
        verbose('Checking if it\'s possible to use the "sudo" command')

        assert len(self._docker_command) == 1

        try:
            proc.check_output(
                self._sudo_command +
                self._docker_command +
                ['version'])
        except (OSError, proc.CalledProcessError) as exc:
            verbose('Cannot use "sudo": %s.' % exc)
            return False

        return True

    def _ensure_docker(self):
        '''
        Check whether we can use the Docker command.
        '''
        if self._did_check_docker:
            return

        self._did_check_docker = True

        verbose('Checking for Docker availability.')

        status = self._try_docker()

        if status == self._DOCKER_SUCCESS:
            return

        elif status == self._DOCKER_NO_COMMAND:
            if sys.platform == 'darwin':
                install_url = 'https://docs.docker.com/docker-for-mac/install/'
            else:
                install_url = 'https://docs.docker.com/engine/installation/linux/'
            die(textwrap.dedent(
                '''\
                It looks like Docker is not installed.

                You can install using the tools provided by your operating system or,
                alternatively, install the official Docker release following the
                instructions at <%s>.
                ''') %
                install_url)

        elif status == self._DOCKER_OTHER_ERROR:
            die('Unexpected error while launching Docker.\n'
                'Check it\'s installed correctly.')

        assert status == self._DOCKER_NO_SERVER

        docker_group = self._check_docker_group()

        if docker_group == self._DOCKER_GROUP_CONTAINS_USER:
            die(textwrap.dedent(
                '''\
                It looks like the Docker server is not running.\n
                You can start it (on recent systems) with this command:

                    sudo systemctl start docker


                If this doesn't work, please read the documentation provided by Docker
                at <https://docs.docker.com/engine/admin/>.
                '''))

        elif docker_group == self._DOCKER_GROUP_UNAVAILABLE:
            # On macOS there's no "docker" group.
            die(textwrap.dedent(
                '''\
                It looks like the Docker server is not running.

                1 - Start the Docker app.
                2 - Make sure the Docker whale icon is in the menu bar on the top right.
                3 - Click the icon and make sure it says "Docker is running".
                '''))

        elif docker_group == self._DOCKER_GROUP_DOES_NOT_EXIST:
            # The group doesn't exist even if Docker is installed.
            # This is probably Fedora or similar using their own packages.
            if self._can_use_sudo():
                self._docker_command = self._sudo_command + self._docker_command
            else:
                die(textwrap.dedent(
                    '''\
                    Cannot run Docker without "sudo".

                    The maintainers of your distribution decided that, for security
                    reasons, users should not be allowed to launch Docker without using the
                    "sudo" command.

                    You have two choices, either configure "sudo" to allow the execution of
                    the "docker" command without a password, or add a "docker" user to the
                    systems. For instructions, see
                    <https://developer.fedoraproject.org/tools/docker/docker-installation.html>.

                    Alternatively, you can install the official Docker packages from
                    <https://docs.docker.com/engine/installation/linux/>.
                    '''))

        elif docker_group == self._DOCKER_GROUP_NOT_IN_GROUP:
            # The group does exist, but the user is not in it.
            import getpass
            die(textwrap.dedent(
                '''\
                To be able to use Docker (which is required by Karton), you need to
                add your user the the "docker" group. To do so, type this command:

                    sudo usermod -a -G docker %s
                ''' %
                getpass.getuser()))

        else:
            die('Internal error, invalid Docker group option %s.' % docker_group)

    @staticmethod
    def _fail_later_docker_command(exc):
        '''
        The initial Docker check passed, but then invoking Docker failed with an
        `OSError`.

        This may mean that Docker just disappeared or, more likely, something is
        wrong with Karton.
        '''
        die(textwrap.dedent(
            '''\
            Unexpected error while trying to run Docker: %s.

            Try rerunning this command.
            ''' % exc))

    def call(self, cmd_args, *args, **kwargs):
        '''
        Like `subprocess.call`, but the right command for docker is prepended to the
        arguments.
        '''
        self._ensure_docker()
        try:
            return proc.call(self._docker_command + cmd_args, *args, **kwargs)
        except OSError as exc:
            self._fail_later_docker_command(exc)

    def check_call(self, cmd_args, *args, **kwargs):
        '''
        Like `subprocess.check_call`, but the right command for docker is prepended
        to the arguments.
        '''
        self._ensure_docker()
        try:
            return proc.check_call(self._docker_command + cmd_args, *args, **kwargs)
        except OSError as exc:
            self._fail_later_docker_command(exc)

    def check_output(self, cmd_args, *args, **kwargs):
        '''
        Like `subprocess.check_output`, but the right command for docker is prepended
        to the arguments and standard error is automatically redirected to the retun
        value.

        See `proc.check_output` for details.
        '''
        self._ensure_docker()
        try:
            return proc.check_output(self._docker_command + cmd_args, *args, **kwargs)
        except OSError as exc:
            self._fail_later_docker_command(exc)

    def is_container_running(self, container_id):
        '''
        Whether the container with `container_id` as ID is running or not.

        container_id:
            The ID of the container to query for its status.
        Return value:
            `True` if the container is running, `False` otherwise.
        '''
        verbose('Checking whether Docker container with ID <%s> is running.' % container_id)

        try:
            output = self.check_output(
                ['inspect', '--format={{ .State.Running }}', container_id])
        except proc.CalledProcessError:
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
