# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from __future__ import print_function

import os
import sys
import unittest

import testutils


class InternalTestCase(unittest.TestCase):
    '''
    Test the functions provided internally by the test framework itself.
    '''

    def test_redirector(self):
        def print_out():
            print(print_out.message)

        def sys_stderr_write():
            sys.stderr.write(sys_stderr_write.message + '\n')

        def os_write_1():
            os.write(1, os_write_1.message + '\n')

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
