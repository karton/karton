# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from __future__ import print_function

import os
import subprocess
import sys
import tempfile

from karton import (
    pathutils,
    )

import testutils

from tracked import TrackedTestCase


class InternalTestCase(TrackedTestCase):
    '''
    Test the functions provided internally by the test framework itself.
    '''

    def test_redirector(self):
        def print_out():
            print(print_out.message)

        def sys_stderr_write():
            sys.stderr.write(sys_stderr_write.message + '\n')

        def os_write_1():
            os.write(1, (os_write_1.message + '\n').encode('utf-8'))

        def system_echo():
            os.system('echo "%s"' % system_echo.message)

        output_sources = (
            (print_out, 'This comes from print.'),
            (sys_stderr_write, 'This comes from sys.stderr.write.'),
            (os_write_1, 'This comes from os.write on 1.'),
            (system_echo, 'This comes from echo.'),
            )

        for function, message in output_sources:
            function.message = message

        # Try each output method singularly.
        for function, message in output_sources:
            redirector = testutils.Redirector()
            with redirector:
                function()
            self.assertIn(message + '\n', redirector.content)

        # Try all the output methods together.
        redirector = testutils.Redirector()
        with redirector:
            for function, _ in output_sources:
                function()

        for _, message in output_sources:
            self.assertIn(message + '\n', redirector.content)

    def test_bin_path(self):
        tmpdir = tempfile.mkdtemp()

        def subprocess_check_in_path():
            result = subprocess.check_output(
                ['bash', '-c', 'echo $PATH'],
                universal_newlines=True)
            return result.startswith(tmpdir + ':')

        self.assertNotIn(tmpdir, pathutils.get_system_executable_paths()[0])
        self.assertFalse(subprocess_check_in_path())

        adder = testutils.BinPathAdder(tmpdir)

        self.assertNotIn(tmpdir, pathutils.get_system_executable_paths()[0])
        self.assertFalse(subprocess_check_in_path())

        with adder:
            self.assertEqual(tmpdir, pathutils.get_system_executable_paths()[0])
            self.assertTrue(subprocess_check_in_path())

        self.assertNotIn(tmpdir, pathutils.get_system_executable_paths()[0])
        self.assertFalse(subprocess_check_in_path())

    def test_work_dir(self):
        def get_pwd():
            cmd_pwd = subprocess.check_output(['pwd'], universal_newlines=True).strip()
            py_pwd = os.getcwd()
            self.assertEqual(cmd_pwd, py_pwd)
            return cmd_pwd

        def assert_equal_real_path(path1, path2):
            self.assertEqual(
                os.path.realpath(path1),
                os.path.realpath(path2))

        def assert_not_equal_real_path(path1, path2):
            self.assertNotEqual(
                os.path.realpath(path1),
                os.path.realpath(path2))

        initial_dir = get_pwd()
        assert_not_equal_real_path(initial_dir, '/')

        with testutils.WorkDir('/'):
            assert_equal_real_path(get_pwd(), '/')

        assert_equal_real_path(get_pwd(), initial_dir)

        with testutils.WorkDir('/var'):
            assert_equal_real_path(get_pwd(), '/var')
            with testutils.WorkDir('/etc'):
                assert_equal_real_path(get_pwd(), '/etc')
            assert_equal_real_path(get_pwd(), '/var')
            os.chdir('/etc')
            assert_equal_real_path(get_pwd(), '/etc')

        assert_equal_real_path(get_pwd(), initial_dir)
