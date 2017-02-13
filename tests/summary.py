#! /usr/bin/env python
#
# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from __future__ import print_function

import glob
import json
import os


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
        results = json.load(results_file)

    summary['target-count'] += 1
    summary['pass-count'] += results['pass-count']
    summary['fail-count'] += results['fail-count']
    summary['error-count'] += results['error-count']
    summary['total-count'] += results['total-count']

    failure_details = summary['failure-details']

    for test_name, details in results['details'].iteritems():
        if details['passed']:
            continue

        if test_name not in failure_details:
            failure_details[test_name] = []

        # We should have one OR the other, not both.
        # We don't bother distinguishing between errors and failures.
        failure_string = details.get('failure')
        error_string = details.get('error')
        assert bool(failure_string) != bool(error_string)

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

    if result == 'PASSED':
        summary['sanity-pass-count'] += 1

    elif result == 'SKIPPED':
        summary['sanity-skip-count'] += 1

    elif result == 'FAILED':
        summary['sanity-fail-count'] += 1
        summary['sanity-failure-details'].append({
            'target': target,
            'log': ''.join(lines[5:])
            })

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
        }

    for path in glob.glob('test-results/*.json'):
        filename = os.path.basename(path)
        if filename == 'summary.json':
            continue
        elif filename == 'local.json':
            target = 'local'
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
        for test_name, details in summary['failure-details'].iteritems():
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
        print('FAILED (%s failures, %d errors, %d sanity failures)' %
              (summary['fail-count'],
               summary['error-count'],
               summary['sanity-fail-count']))
    else:
        print_counts()
        print('SUCCESS')


if __name__ == '__main__':
    main()
