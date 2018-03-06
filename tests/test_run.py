# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import sys
import textwrap
import time
import unittest

from karton import (
    defprops,
    pathutils,
    )

from mixin_docker import DockerMixin
from mixin_dockerfile import DockerfileMixin
from testutils import WorkDir
from tracked import TrackedTestCase


TEST_C_SOURCE = '''\
#include <stdio.h>

#ifndef __linux
#error "This is not Linux!"
#endif

int main(int argc,
         char **argv)
{
    printf("Pointer size: %d\\n", (int)sizeof(void *));
    return 0;
}
'''

class RunTestCase(DockerMixin,
                  DockerfileMixin,
                  TrackedTestCase):
    '''
    Test the run/start/stop commands.
    '''

    def test_fail_build(self):
        def setup_image(props):
            props.distro = 'INVALID'

        self.add_and_build(self.make_image_name('should-fail'),
                           setup_image,
                           ignore_build_fail=True)
        self.assert_exit_fail()
        self.assertIn('DefinitionError: Invalid distro name: "INVALID"\n', self.current_text)

    def test_start_stop(self):
        image_name = self.build_ubuntu_latest_with_gcc()

        self.assert_not_running(image_name)

        self.run_karton(['start', image_name])
        self.assert_running_with_no_commands(image_name)

        self.run_karton(['start', image_name])
        self.assert_running_with_no_commands(image_name)

        self.run_karton(['stop', image_name])
        self.assert_not_running(image_name)

        self.run_karton(['start', image_name])
        self.assert_running_with_no_commands(image_name)

        self.run_karton(['stop', image_name])
        self.assert_not_running(image_name)

    def test_run(self):
        image_name = self.build_ubuntu_latest_with_gcc()
        self.assert_not_running(image_name)

        self.run_karton(['run', '--no-cd', image_name, 'cat', '/etc/issue'])
        self.assertIn('Ubuntu', self.current_text)

        self.assert_running_with_no_commands(image_name)

    def test_shared_dir(self):
        image_name = self.build_ubuntu_devel_with_shared_dirs()
        props = self.cached_props[image_name]

        self.run_karton(['run', '--no-cd', image_name, 'ls',
                         os.path.dirname(props.test_shared_dir_image)])
        self.assertIn(os.path.basename(props.test_shared_dir_image), self.current_text)

        file_in_dir_host_path = os.path.join(props.test_shared_dir_host, 'aFile')
        file_in_dir_image_path = os.path.join(props.test_shared_dir_image, 'aFile')

        self.assertFalse(os.path.exists(file_in_dir_host_path))

        self.run_karton(['run', '--no-cd', image_name, 'cat', file_in_dir_image_path],
                        ignore_fail=True)

        content = 'This is some content'
        with open(file_in_dir_host_path, 'w') as shared_file:
            shared_file.write(content)

        self.run_karton(['run', '--no-cd', image_name, 'cat', file_in_dir_image_path])
        self.assertIn(content, self.current_text)

        self.run_karton(['run', '--no-cd', image_name, 'rm', file_in_dir_image_path])
        self.assertFalse(os.path.exists(file_in_dir_host_path))

    def test_shared_file(self):
        image_name = self.build_ubuntu_devel_with_shared_dirs()
        props = self.cached_props[image_name]

        self.run_karton(['run', '--no-cd', image_name, 'cat', props.test_shared_file_image])
        self.assertIn(props.test_file_content, self.current_text)

        new_content = 'This is some new content'
        with open(props.test_shared_file_host, 'w') as test_file:
            test_file.write(new_content)

        self.run_karton(['run', '--no-cd', image_name, 'cat', props.test_shared_file_image])
        self.assertNotIn(props.test_file_content, self.current_text)
        self.assertIn(new_content, self.current_text)

    def test_copy(self):
        image_name = self.build_ubuntu_devel_with_shared_dirs()
        props = self.cached_props[image_name]

        self.run_karton(['run', '--no-cd', image_name, 'cat',
                         props.test_file_in_copied_dir_image])
        self.assertIn(props.test_file_content, self.current_text)

        self.run_karton(['run', '--no-cd', image_name, 'cat', props.test_copied_file_image])
        self.assertIn(props.test_file_content, self.current_text)

        # The file is copied, so changes on the host are not propagated.
        new_content = 'This is some new content on the host'
        with open(props.test_copied_file_host, 'w') as test_file:
            test_file.write(new_content)

        self.run_karton(['run', '--no-cd', image_name, 'cat', props.test_copied_file_image])
        self.assertIn(props.test_file_content, self.current_text)
        self.assertNotIn(new_content, self.current_text)

    def run_compilation_test(self, image_name, special_flags, expected_pointer_size,
                             expected_file_output):
        props = self.cached_props[image_name]

        host_dir = props.image_home_path_on_host
        image_dir = props.user_home
        source_filename = 'source-file.c'
        exe_filename = 'program'

        pathutils.makedirs(host_dir)

        with open(os.path.join(host_dir, source_filename), 'w') as source_file:
            source_file.write(TEST_C_SOURCE)

        gcc_args = [
            'run',
            '--no-cd',
            image_name,
            'gcc',
            ]

        if special_flags:
            gcc_args += special_flags

        gcc_args += [
            '-o',
            os.path.join(image_dir, exe_filename),
            os.path.join(image_dir, source_filename),
            ]

        self.run_karton(gcc_args)

        self.assertTrue(os.path.exists(os.path.join(host_dir, exe_filename)))

        self.run_karton([
            'run',
            '--no-cd',
            image_name,
            os.path.join(image_dir, exe_filename)
            ])
        self.assertIn('Pointer size: %d' % expected_pointer_size, self.current_text)

        self.run_karton([
            'run',
            '--no-cd',
            image_name,
            'file',
            os.path.join(image_dir, exe_filename),
            ])
        self.assertIn(expected_file_output, self.current_text)

    def test_gcc(self):
        image_name = self.build_ubuntu_latest_with_gcc()
        self.run_compilation_test(
            image_name,
            None,
            8,
            'ELF 64-bit LSB executable, x86-64')

    def test_gcc_x32(self):
        image_name = self.build_ubuntu_old_with_gcc_x32()
        self.run_compilation_test(
            image_name,
            ['-m32'],
            4,
            'ELF 32-bit LSB  executable, Intel 80386')

    def test_sudo(self):
        with_sudo_image_name = self.build_ubuntu_latest_with_gcc()
        self.run_karton(['run', '--no-cd', with_sudo_image_name, 'sudo', 'true'])

        without_sudo_image_name = self.build_debian_latest_without_sudo()
        self.spawn_karton(['run', '--no-cd', without_sudo_image_name, 'sudo', 'pwd'],
                          ignore_fail=True)
        self.assert_exit_fail()
        self.assertIn('Cannot execute "sudo"', self.current_text)

        self.spawn_karton(['run', '--no-cd', without_sudo_image_name, 'cat', '/etc/sudoers'],
                          ignore_fail=True)
        self.assertIn('No such file or directory', self.current_text)

    def test_fedora(self):
        image_name = self.build_fedora_latest()

        self.spawn_karton(['run', '--no-cd', image_name, 'which', 'yum'])
        self.assertIn('/usr/bin/yum', self.current_text)

        self.spawn_karton(['run', '--no-cd', image_name, 'id'])
        self.assertIn('uid=1234(testFedoraUser) ' +
                      'gid=1234(testFedoraUser) ' +
                      'groups=1234(testFedoraUser)',
                      self.current_text)

    @unittest.skip('aarch64 support seems broken for both Ubuntu and Fedora at the moment')
    def test_aarch64(self):
        image_name = self.build_current_aarch64_with_gcc()
        self.run_compilation_test(
            image_name,
            None,
            8,
            'ELF 64-bit LSB executable, ARM aarch64')

    def test_armv7(self):
        image_name = self.build_current_armv7_with_gcc()
        self.run_compilation_test(
            image_name,
            None,
            4,
            'ELF 32-bit LSB executable, ARM, EABI5')

    # This test tests a workaround for OS X. It would not work on Linux as setting the
    # time in the container also sets it on the host.
    @unittest.skipUnless(sys.platform == 'darwin',
                         'date syncing is only needed on macOS')
    def test_date(self):
        image_name = self.build_ubuntu_latest_with_gcc()

        def now():
            return int(time.time())

        def image_time():
            self.run_karton(['run', '--no-cd', image_name, 'date', '+%s'])
            return int(self.current_text)

        def assert_time_correct():
            image_time_now = image_time()
            host_time_now = now()
            self.assertTrue(host_time_now - 1 <= image_time_now <= host_time_now + 10)

        def do_nothing_in_image():
            # Updating time is done in parallel, so we make sure there's ernough time
            # to actually do it.
            self.run_karton(['run', '--no-cd', image_name, 'sleep', '5'])

        do_nothing_in_image() # Force the time to be initially correct.
        assert_time_correct()

        # Set some random time in September 2001 (i.e. force the time to be wrong).
        self.run_karton(['run', '--no-cd', image_name, 'sudo', 'date', '-s', '@1000000000'])
        self.assertIn('2001', self.current_text)

        do_nothing_in_image() # Make the time correct.
        assert_time_correct()

    def test_cd(self):
        image_name = self.build_ubuntu_latest_with_gcc()
        self.assert_not_running(image_name)

        shared_host_path = os.path.join(self.tmp_dir, 'shared')
        shared_image_path = '/shared'
        home_dir = '/foo/bar/testUserHome'

        class Error(object):
            pass

        error = Error()

        def assert_karton_pwd(cd_mode, expected_dir):
            cmd = ['run', image_name, 'pwd']
            if cd_mode is not None:
                cmd.insert(1, cd_mode)

            ignore_fail = (expected_dir is error)

            self.run_karton(cmd, ignore_fail=ignore_fail)

            if expected_dir is error:
                self.assertIn('cannot be accessed in the image', self.current_text)
            else:
                self.assertEqual(expected_dir, self.current_text.strip())

        assert_karton_pwd('--no-cd', home_dir)
        assert_karton_pwd('--auto-cd', home_dir)
        assert_karton_pwd(None, error)

        with WorkDir(shared_host_path):
            assert_karton_pwd('--no-cd', home_dir)
            assert_karton_pwd('--auto-cd', shared_image_path)
            assert_karton_pwd(None, shared_image_path)

        shared_host_subdir_path = os.path.join(shared_host_path, 'subdir')
        shared_image_subdir_path = os.path.join(shared_image_path, 'subdir')
        pathutils.makedirs(shared_host_subdir_path)
        with WorkDir(shared_host_subdir_path):
            assert_karton_pwd('--no-cd', home_dir)
            assert_karton_pwd('--auto-cd', shared_image_subdir_path)
            assert_karton_pwd(None, shared_image_subdir_path)

    def test_at_build_commands(self):
        image_name = self.build_ubuntu_latest_with_commands()

        run_times = (
            defprops.DefinitionProperties.RUN_AT_BUILD_START,
            defprops.DefinitionProperties.RUN_AT_BUILD_BEFORE_USER_PKGS,
            defprops.DefinitionProperties.RUN_AT_BUILD_END,
            )

        for when in run_times:
            self.run_karton([
                'run',
                '--no-cd',
                image_name,
                'test',
                '-e',
                '/%s' % when,
                ])

        self.run_karton([
            'run',
            '--no-cd',
            image_name,
            'ls',
            '/this has spaces/',
            ])
        self.assertIn('\na file with spaces\n', self.current_text)


    def test_non_at_build_commands(self):
        image_name = self.build_ubuntu_latest_with_commands()

        command_text = 'ACTUAL-COMMAND-OUTPUT'

        self.run_karton(['run', '--no-cd', image_name, 'echo', command_text])
        self.assertEqual(
            self.current_text,
            textwrap.dedent('''\
                RUNNING %(start)s
                RUNNING %(before)s
                %(actual)s
                RUNNING %(after)s
                ANOTHER AFTER. escape? (\\)
                ''') % dict(
                    start=defprops.DefinitionProperties.RUN_AT_START,
                    before=defprops.DefinitionProperties.RUN_BEFORE_COMMAND,
                    actual=command_text,
                    after=defprops.DefinitionProperties.RUN_AFTER_COMMAND,
                    ))

        # Same, but:
        # - The container is already started, so the RUN_AT_START output should not be there.
        # - We run a command which returns false.
        self.run_karton(['run', '--no-cd', image_name, 'false'],
                        ignore_fail=True)
        self.assertEqual(
            self.current_text,
            textwrap.dedent('''\
                RUNNING %(before)s
                RUNNING %(after)s
                ANOTHER AFTER. escape? (\\)
                ''') % dict(
                    before=defprops.DefinitionProperties.RUN_BEFORE_COMMAND,
                    after=defprops.DefinitionProperties.RUN_AFTER_COMMAND,
                    ))

        self.run_karton([
            'stop',
            image_name,
            ])
        self.assertEqual('RUNNING %s' % defprops.DefinitionProperties.RUN_AT_STOP,
                         self.current_text.strip())

    def test_env(self):
        image_name = self.build_ubuntu_latest_with_gcc()

        def get_env(*args):
            cmd = ['run', '--no-cd', image_name]
            cmd.extend(args)
            cmd.append('env')
            self.run_karton(cmd)
            return self.current_text

        self.assertIn('\nA=42\n', get_env('A=42'))
        self.assertIn('\nA=42\n', get_env('B=12', 'A=42'))
        self.assertIn('\nA=42\n', get_env('B=12', 'A=42', 'C=hello'))
        self.assertIn('\nA0=42\n', get_env('A0=42'))
        self.assertIn('\nA_0=42\n', get_env('A_0=42'))
        self.assertIn('\n_0=42\n', get_env('_0=42'))
        self.assertIn('\nA=42=123\n', get_env('A=42=123'))
        self.assertIn('\nA=hello world\n', get_env('B=12', 'A=hello world', 'C=hello'))
        self.assertIn('\nA=hello\\ world\n', get_env('B=12', 'A=hello\\ world', 'C=hello'))
        self.assertIn('\nA="hello" \'world\'\n', get_env('B=12', 'A="hello" \'world\'', 'C=hello'))
        self.assertIn('\nLongVariableName=42\n', get_env('LongVariableName=42'))
        self.assertIn('\nUSER=testUser\n', get_env())
        self.assertIn('\nUSER=testUser\n', get_env('A=42'))
        self.assertIn('\nUSER=otherUser\n', get_env('A=42', 'USER=otherUser'))

        # When an argument without "=" in it is found, we need to stop processing.
        self.run_karton(['run', '--no-cd', image_name, 'A=12', 'echo', 'B=NotAVariable'])
        self.assertEqual('B=NotAVariable\n', self.current_text)

        # Stopping variable processing with "--".
        self.run_karton(['run', '--no-cd', image_name, 'A=12', '--', 'A=not an env', 'true'],
                        ignore_fail=True)
        self.assert_exit_fail()
        self.assertIn('Cannot execute "A=not an env".', self.current_text)

        # Check invalid variable names which shouldn't be detected as variables.
        invalid_vars = [
            './A=12',
            '0A=12',
            'A-=12',
            'A-B=12',
            '0=0',
            ]
        for var in invalid_vars:
            self.run_karton(['run', '--no-cd', image_name, var, 'true'],
                            ignore_fail=True)
            self.assert_exit_fail()
            self.assertIn('Cannot execute "%s".' % var, self.current_text)
