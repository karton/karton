# Copyright (C) 2018 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import textwrap

from karton import (
    dockerctl,
    pathutils,
    )

from mixin_dockerfile import DockerfileMixin


class FakeDocker(dockerctl.Docker):
    '''
    Replacement for dockerctl.Docker which allows us to control the
    command line options.
    '''

    def __init__(self, tmp_dir):
        fake_docker_path = os.path.join(tmp_dir, 'fake-docker')

        self._output_dir = os.path.join(tmp_dir, 'docker-output')
        pathutils.makedirs(self._output_dir)

        with open(fake_docker_path, 'w') as fake_docker_file:
            fake_docker_file.write(textwrap.dedent(
                '''\
                #! /bin/bash

                cmd="$1"

                case "$cmd" in
                    images | run )
                        echo "FAKE_IMAGE_ID"
                esac

                case "$cmd" in
                    images | run | build | exec )
                        output_file="%(output_dir)s/$cmd"
                        rm -r "$output_file" 2> /dev/null

                        for arg in "$@"; do
                            echo "$arg" >> "$output_file"
                        done

                        exit 0
                        ;;

                    * )
                        exit 1
                esac
                ''' % dict(
                    output_dir=self._output_dir,
                    )))
            os.fchmod(fake_docker_file.fileno(), 0o755)

        super(FakeDocker, self).__init__()
        self._docker_command = [fake_docker_path]

    def _ensure_docker(self):
        pass

    def get_last_command(self, cmd_name):
        '''
        See `FakeDockerMixin.get_last_command`.
        '''
        cmd_path = os.path.join(self._output_dir, cmd_name)

        try:
            with open(cmd_path) as cmd_file:
                return [line.strip() for line in cmd_file.readlines()]
        except IOError:
            return []


class FakeDockerMixin(DockerfileMixin):
    '''
    A mixin to replace real Docker with an implementation which writes the command
    line arguments to a file.
    '''

    def create_docker(self):
        return FakeDocker(self.make_tmp_sub_dir('fake-docker-bin'))

    def get_last_command(self, cmd_name):
        '''
        Get the arguments passed to the fake docker executable last time `cmd_name`
        was used.

        cmd_name:
            The command passed to Karton which resulted in Docker being
            run.
        Return value:
            The command line passed to Docker as a list of strings.
            An empty list if the command was never used.
        '''
        return self.docker.get_last_command(cmd_name)
