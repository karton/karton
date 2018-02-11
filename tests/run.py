#! /usr/bin/env python
#
# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import json
import os
import sys
import unittest

import tracked


# Keep this ordered from the fast and more low level ones to the ones which
# require a full image build/run/etc.
ALL_TESTS = [
    'test_internal',
    'test_no_image',
    'test_docker_check',
    'test_dockerfile',
    'test_images',
    'test_run',
    'test_alias',
    'test_consistency',
    ]


def summarize_results(result):
    '''
    Given a `unittest.TestResult`, produces a dictionary (suitable for JSON serialization) with
    a summary of the tests failures, errors and passed tests.

    result:
        A `unittest.TestResult`.
    Return value:
        A dictionary suitable for JSON serialization.
    '''
    test_details = {}
    for test_name in tracked.TrackedTestCase.all_run_tests:
        test_details[test_name] = {'passed': True}

    for test, exception_string in result.failures:
        test_name = test.id()
        assert test_name in test_details
        test_test_details = test_details[test_name]

        test_test_details['passed'] = False
        test_test_details['fail-style'] = 'failure'
        test_test_details['failure'] = exception_string

    for test, exception_string in result.errors:
        test_name = test.id()
        assert test_name in test_details
        test_test_details = test_details[test_name]

        # A test cannot fail and give an error as well.
        assert test_test_details['passed']

        test_test_details['passed'] = False
        test_test_details['fail-style'] = 'error'
        test_test_details['error'] = exception_string

    fail_count = len(result.failures)
    error_count = len(result.errors)
    total_count = len(tracked.TrackedTestCase.all_run_tests)
    pass_count = total_count - fail_count - error_count

    return {
        'pass-count': pass_count,
        'fail-count': fail_count,
        'error-count': error_count,
        'total-count': total_count,
        'ok': pass_count == total_count,
        'details': test_details,
        }


def main(argv):
    '''
    Run tests with the specified command line options.

    argv:
        The arguments to use to run tests, for instance `sys.argv`. If no tests are specified,
        then all tests are run.
    Return value:
        True if all the specified tests passed, False oterwise.
    '''
    # We deal with some special private arguments and ignore everything else so we can
    # pass it to unittest. This is not the ideal way of parsing arguments but it works...
    filtered_argv = [argv[0]]
    i = 1
    json_result_path = None
    has_test_name = False
    while i < len(argv):
        arg = argv[i]
        i += 1
        if arg == '--save-json-results':
            try:
                json_result_path = os.path.abspath(argv[i])
            except IndexError:
                raise Exception('Argument for "--save-json-results" missing.')
            i += 1
        else:
            if not arg.startswith('-'):
                has_test_name = True
            filtered_argv.append(arg)

    if not has_test_name:
        # No test name was explicitly passed, so we just run everything.
        filtered_argv.extend(ALL_TESTS)

    # We use an environment variable as it's the most convenient way of setting the option
    # when executing make.
    if os.environ.get('V'):
        # Add -v after the script name.
        filtered_argv.insert(1, '-v')

    # To avoid adding "tests." in front of all the modules, we just change directory to the
    # test one and add the top-level directory to the paths so karton can be imported easily.
    os.chdir('tests')
    sys.path.insert(0, '..')

    # Let unittest run the tests as normal.
    test_program = unittest.main(module=None, exit=False, argv=filtered_argv)
    result = test_program.result

    if json_result_path:
        json_dict = summarize_results(result)
        with open(json_result_path, 'w') as json_file:
            json.dump(json_dict,
                      json_file,
                      indent=4,
                      separators=(',', ': '))

    return result.wasSuccessful()


if __name__ == '__main__':
    if not main(sys.argv):
        raise SystemExit(1)
