# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import subprocess

from karton import (
    dockerctl,
    )

from mixin_karton import KartonMixin


def make_image(main_image_name):
    '''
    Decorator for methods which setup an image.

    The decorated method should accept a `DefinitionProperties` instance.

    main_image_name:
        An identifier for the images which is used to build the actual image name.
    '''
    def real_decorator(function):
        def actual_method(self):
            image_name = self.make_image_name(main_image_name)

            def setup_image(props):
                function(self, props)

                self.assertNotIn(image_name, self.cached_props)
                self.cached_props[image_name] = props

            self.add_and_build(image_name, setup_image)

            return image_name

        return actual_method

    return real_decorator


class DockerMixin(KartonMixin):
    '''
    Mixin which takes care of Docker-related issues and allow to generate images.
    '''

    # This is a prefix to distinguish easily our images form non-test ones.
    TEST_IMAGE_PREFIX = 'karton-test-'

    def __init__(self, *args, **kwargs):
        super(DockerMixin, self).__init__(*args, **kwargs)

        self.cached_props = None

    def setUp(self):
        super(DockerMixin, self).setUp()

        # We clear on setUp as well in case the previous test run failed to
        # clean-up properly.
        self.clear_running_test_containers()

        self.cached_props = {}

    def tearDown(self):
        self.clear_running_test_containers()
        super(DockerMixin, self).tearDown()

    def create_docker(self):
        return dockerctl.Docker()

    def clear_running_test_containers(self):
        '''
        Stop all the test Docker containers.
        '''
        for container_id in self.get_running_test_containers():
            subprocess.check_output(
                ['docker',
                 'stop',
                 container_id,
                ])

    @staticmethod
    def get_running_test_containers():
        '''
        List all the running test Docker containers.

        Return value:
            A list of container IDs.
        '''
        # --filter doesn't accept wildcards nor a regexp.
        output = subprocess.check_output(
            ['docker',
             'ps',
             '--format',
             '{{ .ID }}:{{ .Image }}',
            ])

        ids = []
        for line in output.split('\n'):
            if not line:
                continue
            container_id, image_name = line.split(':', 1)
            if image_name.startswith(DockerMixin.TEST_IMAGE_PREFIX):
                ids.append(container_id)

        return ids

    @staticmethod
    def make_image_name(main_name_component):
        '''
        Make an image name which contains `main_name_component` in it.

        main_name_component:
            An identifier for the image.
        Return value:
            An image name.
        '''
        return DockerMixin.TEST_IMAGE_PREFIX + main_name_component

    def assert_running(self, image_name):
        '''
        Assert that the image called `image_name` is running.

        image_name:
            The image to check.
        '''
        status = self.get_status(image_name)
        self.assertTrue(status['running'])
        self.assertIn('commands', status)
        return status['commands']

    def assert_running_with_no_commands(self, image_name):
        '''
        Assert that the image called `=image_name` is running, but that no
        command is running inside it.

        image_name:
            The image to check.
        '''
        commands = self.assert_running(image_name)
        self.assertEqual(len(commands), 0)

    def assert_not_running(self, image_name):
        '''
        Assert that the image called `image_name` is not running.

        image_name:
            The image to check.
        '''
        status = self.get_status(image_name)
        self.assertFalse(status['running'])

    def add_and_build(self, image_name, setup_image, ignore_build_fail=False):
        '''
        Add an image called `image_name`.

        image_name:
            The name of the image to add.
        setup_image:
            The setup function for the image definition.
        ignore_build_fail:
            If true, build errors are ignored.
            Otherwise, an assert is triggered in case of failure.
        '''
        assert image_name.startswith(DockerMixin.TEST_IMAGE_PREFIX)

        import_info = self.prepare_for_image_import(setup_image)
        self.run_karton(['image', 'import', image_name, import_info.definition_dir])
        self.run_karton(['build', image_name], ignore_fail=ignore_build_fail)

    # This is needed because pylint gets confused by decorators.
    #pylint: disable=no-self-use

    @make_image('ubuntu-gcc')
    def build_ubuntu_latest_with_gcc(self, props=None):
        props.distro = 'ubuntu'
        props.packages.append('gcc')

    @make_image('ubuntu-gcc-x32')
    def build_ubuntu_old_with_gcc_x32(self, props=None):
        props.distro = 'ubuntu:trusty'
        props.packages.extend(['gcc', 'gcc-multilib'])

    # We cannot skip the build stage as we need to generate some on-disk content.
    @make_image('ubuntu-shared-dirs')
    def build_ubuntu_devel_with_shared_dirs(self, props=None):
        props.distro = 'ubuntu:devel'

        props.test_shared_dir_host = os.path.join(self.tmp_dir, 'test-shared-directory')
        props.test_shared_dir_image = '/test-shared-directory'
        props.share_path(props.test_shared_dir_host, props.test_shared_dir_image)

        props.test_shared_file_host = os.path.join(self.tmp_dir, 'test-shared-file')
        props.test_shared_file_image = '/etc/test-shared-file'
        props.share_path(props.test_shared_file_host, props.test_shared_file_image)

        props.test_file_content = 'Hello world!'
        with open(props.test_shared_file_host, 'w') as test_file:
            test_file.write(props.test_file_content)

    @make_image('debian-no-sudo')
    def build_debian_latest_without_sudo(self, props=None):
        props.distro = 'debian'
        props.sudo = props.SUDO_NO
