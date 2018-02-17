# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import json
import os
import pipes
import textwrap

from karton import (
    dockerctl,
    )

from mixin_dockerfile import DockerfileMixin
from testutils import OverwriteVersion
from tracked import TrackedTestCase


class FakeDocker(dockerctl.Docker):
    '''
    Replacement for dockerctl.Docker which allow the generation of errors,
    like if Docker was not availabe, the server not running, etc.
    '''

    def __init__(self, tmp_dir):
        self._stdout_path = os.path.join(tmp_dir, 'fake-docker.stdout')
        self._stderr_path = os.path.join(tmp_dir, 'fake-docker.stderr')
        self._fake_docker_path = os.path.join(tmp_dir, 'fake-docker')

        self._fake_sudo_path = os.path.join(tmp_dir, 'fake-sudo')
        self.set_sudo_result(2, 'Unexpected call to "sudo".')

        self._has_docker_group = False
        self._in_docker_group = False
        self.docker_group = 'INVALID'

        super(FakeDocker, self).__init__()
        self._docker_command = [self._fake_docker_path]
        self._sudo_command = [self._fake_sudo_path, '-n']

    @property
    def command_length(self):
        return len(self._docker_command)

    def _check_docker_group(self):
        return self.docker_group

    def set_versions(self, client_version, server_version):
        json_dict = {}

        def version_dict(version):
            if version is None:
                return None
            else:
                return {'Version': version}

        json_dict['Client'] = version_dict(client_version)
        json_dict['Server'] = version_dict(server_version)

        with open(self._stdout_path, 'w') as stdout_file:
            json.dump(json_dict, stdout_file)

        with open(self._stderr_path, 'w') as stderr_file:
            if server_version is None:
                stderr_file.write('Error response from daemon: Bad response from Docker engine')

        with open(self._fake_docker_path, 'w') as fake_docker_file:
            fake_docker_file.write(textwrap.dedent(
                '''\
                #! /bin/bash

                if [ "$1" != "version" ]; then
                    echo "Expected 'version', got '$1'" >&2
                    exit 1
                fi

                cat "$0.stdout"
                cat "$0.stderr" >&2
                '''))
            os.fchmod(fake_docker_file.fileno(), 0o755)

    def set_sudo_result(self, exit_code, output=''):
        with open(self._fake_sudo_path, 'w') as fake_sudo_file:
            fake_sudo_file.write(textwrap.dedent(
                '''\
                #! /bin/bash

                output=%(output)s
                if [ -n "$output" ]; then
                    echo "$output"
                fi

                if [ "$1" != "-n" ]; then
                    echo "The first argument should be '-n' but was '$1'" >&2
                fi

                if [ "$2" != "%(docker_path)s" ]; then
                    echo "The second argument should be '%(docker_path)s' but was '$2'" >&2
                fi

                exit %(exit_code)d
                ''' % dict(
                    output=pipes.quote(output),
                    exit_code=exit_code,
                    docker_path=self._fake_docker_path,
                    )))
            os.fchmod(fake_sudo_file.fileno(), 0o755)


class DockerCheckTestCase(DockerfileMixin,
                          TrackedTestCase):
    '''
    Test that we recognise correctly how to run Docker and its availability.
    '''

    def create_docker(self):
        return FakeDocker(self.make_tmp_sub_dir('fake-docker-bin'))

    def setUp(self):
        super(DockerCheckTestCase, self).setUp()

        # Add a dummy image to Karton *without* calling docker.

        def setup_image(props):
            pass

        import_info = self.prepare_for_image_import(setup_image)

        self._image_name = 'test-dummy-image'
        self.run_karton(['image', 'import', self._image_name, import_info.definition_dir])

    def try_run(self):
        with OverwriteVersion():
            self.run_karton(['run', '--no-cd', self._image_name, 'true'], ignore_fail=True)

    def test_no_docker(self):
        self.try_run()
        self.assert_exit_fail()
        self.assertIn('It looks like Docker is not installed.', self.current_text)

    def test_no_client(self):
        self.docker.set_versions(None, '1.2.3-X')
        self.try_run()
        self.assert_exit_fail()
        self.assertIn('Unexpected error while launching Docker.', self.current_text)

    # We need this to overwite the normal dockerctl.Docker behaviour.
    #pylint: disable=protected-access

    def test_group_unavailable(self):
        self.docker.set_versions('1.2.3-X', None)
        self.docker.docker_group = self.docker._DOCKER_GROUP_UNAVAILABLE
        self.try_run()
        self.assert_exit_fail()
        self.assertIn('It looks like the Docker server is not running.', self.current_text)

    def test_sudo_not_available(self):
        self.docker.set_versions('1.2.3-X', None)
        self.docker.docker_group = self.docker._DOCKER_GROUP_DOES_NOT_EXIST
        self.docker.set_sudo_result(1, 'sudo: a password is required')
        self.assertEqual(self.docker.command_length, 1)
        self.try_run()
        self.assert_exit_fail()
        self.assertIn('Cannot run Docker without "sudo".', self.current_text)
        self.assertEqual(self.docker.command_length, 1)

    def test_sudo_available(self):
        self.docker.set_versions('1.2.3-X', None)
        self.docker.docker_group = self.docker._DOCKER_GROUP_DOES_NOT_EXIST
        fake_sudo_msg = 'This comes from the test fake "sudo".'
        self.docker.set_sudo_result(0, fake_sudo_msg)
        self.assertEqual(self.docker.command_length, 1)
        self.try_run()
        # It succeeds because the fake sudo script succeeds.
        self.assert_exit_success()
        self.assertIn(fake_sudo_msg, self.current_text)
        self.assertEqual(self.docker.command_length, 3)

    def test_not_in_group(self):
        self.docker.set_versions('1.2.3-X', None)
        self.docker.docker_group = self.docker._DOCKER_GROUP_NOT_IN_GROUP
        self.try_run()
        self.assert_exit_fail()
        self.assertIn('sudo usermod -a -G docker', self.current_text)

    def test_in_group_but_no_server(self):
        self.docker.set_versions('1.2.3-X', None)
        self.docker.docker_group = self.docker._DOCKER_GROUP_CONTAINS_USER
        self.try_run()
        self.assert_exit_fail()
        self.assertIn('It looks like the Docker server is not running.', self.current_text)

    def test_success(self):
        self.docker.set_versions('1.2.3-X', '1.2.3-X')
        self.try_run()
        # It fails because our fake Docker cannot run commands.
        self.assert_exit_fail()
        # This means that the check went fine and then we try to re-run our fake docker
        # command to check if the image is available, but our fake docker doesn't
        # understand the "images" command.
        self.assertIn('Expected \'version\', got \'images\'', self.current_text)
