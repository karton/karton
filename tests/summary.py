#! /usr/bin/env python
#
# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from __future__ import print_function

import glob
import json
import os
import sys


def get_target_details(summary, target):
    '''
    Get `summary['targets'][target]` creating it if needed.

    summary:
        The dictionary cotaining the summary of all test results.
    target:
        The name of the target.
    Return value:
        A dictionary with existing target details or a new one with default values.
    '''
    if target.startswith('local'):
        sanity_default = 'N/A'
    else:
        sanity_default = 'unknown'

    if target not in summary['targets']:
        summary['targets'][target] = {
            'pass-count': 0,
            'fail-count': 0,
            'error-count': 0,
            'sanity-result': sanity_default,
            'sanity-ok': True,
            }

    return summary['targets'][target]


def process_results_file(summary, target, results_path):
    '''
    Process a single JSON result file and adds its data to `summary`.

    summary:
        The dictionary cotaining the summary of all test results.
    target:
        The name of the target.
    results_path:
        The path where the results for `target` are.
    '''
    with open(results_path, 'r') as results_file:
        try:
            results = json.load(results_file)
        except ValueError:
            sys.stderr.write('Cannot parse "%s".\n' % results_path)
            raise SystemExit(1)

    summary['target-count'] += 1
    summary['pass-count'] += results['pass-count']
    summary['fail-count'] += results['fail-count']
    summary['error-count'] += results['error-count']
    summary['total-count'] += results['total-count']

    failure_details = summary['failure-details']
    target_details = get_target_details(summary, target)

    for test_name, details in results['details'].items():
        if details['passed']:
            target_details['pass-count'] += 1
            continue

        if test_name not in failure_details:
            failure_details[test_name] = []

        # We should have one OR the other, not both.
        # We don't bother distinguishing between errors and failures.
        failure_string = details.get('failure')
        error_string = details.get('error')
        assert bool(failure_string) != bool(error_string)

        if failure_string:
            target_details['fail-count'] += 1
        if error_string:
            target_details['error-count'] += 1

        exception_string = failure_string or error_string

        failure_details[test_name].append({
            'target': target,
            'exception-string': exception_string,
            })


def process_sanity_file(summary, target, sanity_path):
    '''
    Process a sanity log file and adds its data to `summary`.

    summary:
        The dictionary cotaining the summary of all test results.
    target:
        The name of the target.
    sanity_path:
        The path where the sanity results for `target` are.
    '''
    summary['sanity-count'] += 1

    with open(sanity_path, 'r') as sanity_file:
        lines = sanity_file.readlines()

    result = lines[0].strip()
    target_details = get_target_details(summary, target)

    if result == 'PASSED':
        summary['sanity-pass-count'] += 1
        target_details['sanity-result'] = 'passed'

    elif result == 'SKIPPED':
        summary['sanity-skip-count'] += 1
        target_details['sanity-result'] = 'skipped'

    elif result == 'FAILED':
        summary['sanity-fail-count'] += 1
        summary['sanity-failure-details'].append({
            'target': target,
            'log': ''.join(lines[5:])
            })
        target_details['sanity-result'] = 'failed'
        target_details['sanity-ok'] = False

    else:
        assert False, 'Invalid sanity result: %s' % result


def main():
    '''
    Generates `test-results/summary.json` and prints out a summary as well.
    '''
    summary = {
        'target-count': 0,
        'pass-count': 0,
        'fail-count': 0,
        'error-count': 0,
        'total-count': 0,
        'failure-details': {},

        'sanity-count': 0,
        'sanity-pass-count': 0,
        'sanity-skip-count': 0,
        'sanity-fail-count': 0,
        'sanity-failure-details': [],

        'targets': {},
        }

    for path in glob.glob('test-results/*.json'):
        filename = os.path.basename(path)
        if filename == 'summary.json':
            continue
        elif filename.startswith('local'):
            target = filename[:-len('.json')]
        elif filename.startswith('inception-'):
            target = filename[len('inception-'):-len('.json')]

        process_results_file(summary, target, path)

    for path in glob.glob('test-results/sanity-*.log'):
        filename = os.path.basename(path)
        target = filename[len('sanity-'):-len('.log')]
        process_sanity_file(summary, target, path)

    with open('test-results/summary.json', 'w') as summary_file:
        json.dump(summary,
                  summary_file,
                  indent=4,
                  separators=(',', ': '))

    summary['ok'] = \
        not summary['fail-count'] and \
        not summary['error-count'] and \
        not summary['sanity-fail-count']

    def print_counts():
        print('Ran %d tests and %d sanity checks against %d targets.' %
              (summary['total-count'],
               summary['sanity-count'],
               summary['target-count']))
        print()

    print()
    if not summary['ok']:
        for test_name, details in summary['failure-details'].items():
            print('=' * 70)
            print('FAIL: %s on %d targets' % (test_name, len(details)))
            print('-' * 70)
            for detail in details:
                print('TARGET: %s' % detail['target'])
                print(detail['exception-string'].strip())
                print('-' * 70)
            print()

        for detail in summary['sanity-failure-details']:
            print('=' * 70)
            print('SANITY FAIL on target %s' % detail['target'])
            print('-' * 70)
            log_lines = detail['log'].split('\n')
            max_lines = 12
            if log_lines > max_lines:
                log_lines = detail['log'].split('\n')[-max_lines:]
                log_lines.insert(0, '[...]')
            log = '\n'.join(log_lines)
            print(log.strip())
            print('-' * 70)
            print()

        print_counts()

        def target_cmp((target1, target_details1), (target2, target_details2)):
            # Sort items in summary['targets'] by putting local results first.
            def index_for_target(target):
                if target.startswith('local'):
                    return 0
                else:
                    return 1

            return cmp((index_for_target(target1), target1, target_details1),
                       (index_for_target(target2), target2, target_details2))

        for target, target_details in sorted(summary['targets'].items(), target_cmp):
            target_ok = \
                target_details['fail-count'] == 0 and \
                target_details['error-count'] == 0 and \
                target_details['sanity-ok']
            if target_ok:
                continue

            print(' - %s: %d passed, %d failures, %d errors, sanity: %s' %
                  (target,
                   target_details['pass-count'],
                   target_details['fail-count'],
                   target_details['error-count'],
                   target_details['sanity-result']))

        print()

        print('FAILED (%s failures, %d errors, %d sanity failures)' %
              (summary['fail-count'],
               summary['error-count'],
               summary['sanity-fail-count']))
    else:
        print_counts()
        print('SUCCESS')


if __name__ == '__main__':
    main()
