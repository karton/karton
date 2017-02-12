# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import unittest

class TrackedTestCase(unittest.TestCase):
    '''
    Base unit test case class that adds tracking of which tests are run.
    '''

    # Names of all the tests which were run up until now.
    all_run_tests = set()

    def setUp(self):
        test_name = self.id()
        assert test_name not in TrackedTestCase.all_run_tests
        TrackedTestCase.all_run_tests.add(test_name)

        super(TrackedTestCase, self).setUp()
