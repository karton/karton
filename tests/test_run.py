# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import time
import unittest

from karton import (
    pathutils,
    )

from mixin_docker import DockerMixin
from mixin_dockerfile import DockerfileMixin


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
                  unittest.TestCase):
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
            self.assertTrue(host_time_now - 5 <= image_time_now <= host_time_now + 15)

        def do_nothing_in_image():
            self.run_karton(['run', '--no-cd', image_name, 'true'])

        do_nothing_in_image() # Force the time to be initially correct.
        assert_time_correct()

        # Set some random time in September 2001 (i.e. force the time to be wrong).
        self.run_karton(['run', '--no-cd', image_name, 'sudo', 'date', '-s', '@1000000000'])
        self.assertIn('2001', self.current_text)

        do_nothing_in_image() # Make the time correct.
        self.assertIn('out of sync with the host', self.current_text)
        self.assertIn('Image time: 2001-09-', self.current_text)

        assert_time_correct()
