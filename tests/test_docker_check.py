# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import json
import os
import textwrap

from karton import (
    dockerctl,
    )

from mixin_dockerfile import DockerfileMixin
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

        self._has_docker_group = False
        self._in_docker_group = False
        self.docker_group = 'INVALID'

        super(FakeDocker, self).__init__()
        self._docker_command = self._fake_docker_path

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

    def test_group_does_not_exist(self):
        self.docker.set_versions('1.2.3-X', None)
        self.docker.docker_group = self.docker._DOCKER_GROUP_DOES_NOT_EXIST
        self.try_run()
        self.assert_exit_fail()
        # FIXME.
        self.assertIn('FIXME', self.current_text)

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
        self.assert_exit_fail()
        # This means that the check went fine and then we try to re-run our fake docker
        # command to check if the image is available, but our fake docker doesn't
        # understand the "images" command.
        self.assertIn('Expected \'version\', got \'images\'', self.current_text)
