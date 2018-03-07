# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import platform
import subprocess
import sys

from karton import (
    defprops,
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

    _docker_command = None

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

    def forget_cached_props(self, image_name):
        '''
        Delete the cached properties for `image_name`. This allows the image to be rebuilt.

        image_name:
            The image to forget about.
        '''
        self.assertIn(image_name, self.cached_props)
        del self.cached_props[image_name]

    @staticmethod
    def _ensure_docker_command():
        if DockerMixin._docker_command is not None:
            return

        def run_version():
            try:
                subprocess.check_output(DockerMixin._docker_command + ['version'],
                                        stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError:
                return False
            return True

        DockerMixin._docker_command = ['docker']
        if not run_version():
            DockerMixin._docker_command = ['sudo', '-n'] + DockerMixin._docker_command
            if not run_version():
                raise Exception('Cannot run docker (neither with nor without sudo)')

    @staticmethod
    def _check_output_docker(cmd, *args, **kwargs):
        DockerMixin._ensure_docker_command()

        cmd = DockerMixin._docker_command + cmd
        kwargs['stderr'] = subprocess.STDOUT
        kwargs['universal_newlines'] = True

        return subprocess.check_output(cmd, *args, **kwargs)

    def clear_running_test_containers(self):
        '''
        Stop all the test Docker containers.
        '''
        for container_id in self.get_running_test_containers():
            self._check_output_docker(['stop', container_id])

    @staticmethod
    def get_running_test_containers():
        '''
        List all the running test Docker containers.

        Return value:
            A list of container IDs.
        '''
        # --filter doesn't accept wildcards nor a regexp.
        output = DockerMixin._check_output_docker(
            ['ps',
             '--format',
             '{{ .ID }}:{{ .Image }}'],
            stderr=subprocess.STDOUT)

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

    def get_distro_matching_current(self):
        '''
        Returns the name (in the docker format but without tag) of the distro we are currently
        running on.

        In case this is run on macOS, `ubuntu` is returned.
        '''
        if sys.platform == 'darwin':
            return 'ubuntu'

        # We want to match the currently used distro. Here we could have a fallback, but
        # I don't want to accidentally fallback to something without noticing.
        # If you need to support another distro, please just add something suitable as
        # fallback.

        supported_distros = {
            'Ubuntu': 'ubuntu',
            'debian': 'debian',
            'Fedora': 'fedora',
            'CentOS Linux': 'centos',
            }

        current_distro = platform.linux_distribution()[0]
        if not current_distro:
            self.fail('Unnown distro, cannot run')

        try:
            return supported_distros[current_distro]
        except KeyError:
            self.fail('Unsupported distro "%s"' % current_distro)

    # This is needed because pylint gets confused by decorators.
    #pylint: disable=no-self-use

    @make_image('ubuntu-gcc')
    def build_ubuntu_latest_with_gcc(self, props=None):
        props.distro = 'ubuntu'
        props.packages.extend(['gcc', 'libc6-dev', 'file'])

        props.share_path(os.path.join(self.tmp_dir, 'shared'),
                         '/shared')

    @make_image('ubuntu-gcc-x32')
    def build_ubuntu_old_with_gcc_x32(self, props=None):
        props.distro = 'ubuntu:trusty'
        props.packages.extend(['gcc', 'libc6-dev', 'gcc-multilib', 'file'])

        props.default_consistency = props.CONSISTENCY_CACHED

        props.share_path(os.path.join(self.tmp_dir, 'shared-default'),
                         '/shared-default')
        props.share_path(os.path.join(self.tmp_dir, 'shared-consistent'),
                         '/shared-consistent',
                         props.CONSISTENCY_CONSISTENT)
        props.share_path(os.path.join(self.tmp_dir, 'shared-cached'),
                         '/shared-cached',
                         props.CONSISTENCY_CACHED)
        props.share_path(os.path.join(self.tmp_dir, 'shared-delegated'),
                         '/shared-delegated',
                         props.CONSISTENCY_DELEGATED)

    @make_image('ubuntu-gcc')
    def build_ubuntu_latest_with_commands(self, props=None):
        props.distro = 'ubuntu'

        at_build_run_times_and_prefix = (
            (defprops.DefinitionProperties.RUN_AT_BUILD_START, None),
            (defprops.DefinitionProperties.RUN_AT_BUILD_BEFORE_USER_PKGS, None),
            (defprops.DefinitionProperties.RUN_AT_BUILD_END, 'sudo'),
            )

        for when, prefix in at_build_run_times_and_prefix:
            args = []
            if prefix:
                args.append(prefix)
            args.extend(['touch', '/%s' % when])

            props.run_command(when, *args)

        later_run_times = (
            defprops.DefinitionProperties.RUN_AT_START,
            defprops.DefinitionProperties.RUN_BEFORE_COMMAND,
            defprops.DefinitionProperties.RUN_AFTER_COMMAND,
            defprops.DefinitionProperties.RUN_AT_STOP,
            )

        for when in later_run_times:
            props.run_command(when, 'echo', 'RUNNING %s' % when)

        # Test multiple commands work and that we escape things correctly as well.
        props.run_command(defprops.DefinitionProperties.RUN_AT_BUILD_END,
                          'sudo',
                          'mkdir',
                          '/this has spaces')
        props.run_command(defprops.DefinitionProperties.RUN_AT_BUILD_END,
                          'sudo',
                          'touch',
                          '/this has spaces/a file with spaces')
        props.run_command(defprops.DefinitionProperties.RUN_AFTER_COMMAND,
                          'echo',
                          r'ANOTHER AFTER. escape? (\)')

        # Test that commands returning non-0 after the build is done don't make
        # the command fail.
        props.run_command(defprops.DefinitionProperties.RUN_AFTER_COMMAND,
                          'false')


    # We cannot skip the build stage as we need to generate some on-disk content.
    @make_image('ubuntu-shared-dirs')
    def build_ubuntu_devel_with_shared_dirs(self, props=None):
        props.distro = 'ubuntu:devel'

        # Shared directory.
        props.test_shared_dir_host = os.path.join(self.tmp_dir, 'test-shared-directory')
        props.test_shared_dir_image = '/test-shared-directory'
        props.share_path(props.test_shared_dir_host, props.test_shared_dir_image)

        # Shared file.
        props.test_shared_file_host = os.path.join(self.tmp_dir, 'test-shared-file')
        props.test_shared_file_image = '/etc/test-shared-file'
        # Also verify we deal correctly with relative paths.
        relative_test_shared_file_host = os.path.relpath(
            props.test_shared_file_host,
            os.path.dirname(props.definition_file_path))
        props.share_path(relative_test_shared_file_host, props.test_shared_file_image)
        props.test_file_content = 'Hello world!'
        with open(props.test_shared_file_host, 'w') as test_file:
            test_file.write(props.test_file_content)

        # Copied directory.
        props.test_copied_dir_host = os.path.join(props.definition_file_dir, 'test-copied-dir')
        os.mkdir(props.test_copied_dir_host)
        props.test_file_in_copied_dir_host = os.path.join(props.test_copied_dir_host,
                                                          'file-in-copied-dir')
        with open(props.test_file_in_copied_dir_host, 'w') as test_file:
            test_file.write(props.test_file_content)
        props.test_copied_dir_image = '/this-does-not-exist/copied-dir'
        props.test_file_in_copied_dir_image = os.path.join(
            props.test_copied_dir_image, os.path.basename(props.test_file_in_copied_dir_host))
        props.copy(props.test_copied_dir_host, props.test_copied_dir_image)

        # Copied file.
        props.test_copied_file_host = os.path.join(props.definition_file_dir, 'test-copied-file')
        with open(props.test_copied_file_host, 'w') as test_file:
            test_file.write(props.test_file_content)
        props.test_copied_file_image = '/etc/the-copied-file'
        props.copy(props.test_copied_file_host, props.test_copied_file_image)

    @make_image('debian-no-sudo')
    def build_debian_latest_without_sudo(self, props=None):
        props.distro = 'debian'
        props.sudo = props.SUDO_NO

    @make_image('fedora')
    def build_fedora_latest(self, props=None):
        props.distro = 'fedora:latest'
        props.packages.append('which')
        props.username = 'testFedoraUser'
        props.uid = 1234
        props.user_home = '/foo/bar/testFedoraUserHome'

    def _build_current_with_gcc_for_arch(self, props, arch, unavailable_distros=()):
        props.distro = self.get_distro_matching_current()
        if props.distro_name in unavailable_distros:
            if props.distro_name == 'centos' and 'fedora' not in unavailable_distros:
                props.distro = 'fedora'
            else:
                props.distro = 'ubuntu'
            assert props.distro not in unavailable_distros

        props.architecture = arch

        if props.deb_based:
            props.packages.extend(['gcc', 'libc6-dev', 'file'])
        else:
            props.packages.append('gcc')

    @make_image('aarch64-gcc')
    def build_current_aarch64_with_gcc(self, props=None):
        self._build_current_with_gcc_for_arch(
            props, 'aarch64', ('fedora', 'centos'))

    @make_image('armv7-gcc')
    def build_current_armv7_with_gcc(self, props=None):
        self._build_current_with_gcc_for_arch(
            props, 'armv7', ('fedora', 'centos',))
