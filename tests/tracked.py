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

    def assert_raises_regex(self, *args, **kwargs):
        # In recent Python, assertRaisesRegexp is deprecated in favour of assertRaisesRegex.
        actual_method = getattr(self, 'assertRaisesRegex', self.assertRaisesRegexp)
        return actual_method(*args, **kwargs)

    def assert_items_equal(self, *args, **kwargs):
        # In recent Python, assertItemsEqual was removed in favour of the very confusignly
        # named assertCountEqual.
        actual_method = getattr(self, 'assertCountEqual', None)
        if actual_method is None:
            actual_method = getattr(self, 'assertItemsEqual')
        return actual_method(*args, **kwargs)
