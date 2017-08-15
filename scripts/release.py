#! /usr/bin/env python

from __future__ import print_function

import collections
import datetime
import os
import re
import subprocess
import sys
import tempfile
import textwrap


CHANGELOG_ENTRY = '''\
Karton %(version)s - %(date)s %(author)s <%(email)s>

    * FILL ME!

'''


def die(msg):
    if not msg.endswith('\n'):
        msg += '\n'
    sys.stderr.write(msg)
    raise SystemExit(1)


def print_help():
    print('%s help|prepare|push' % sys.argv[0])


def ask(question, choices=None, allow_empty=False):
    if choices is not None:
        choices_string = '[%s] ' % '/'.join(choices)
    else:
        choices_string = ''

    while True:
        answer = raw_input(question + ' ' + choices_string).strip()

        if not allow_empty and not answer:
            continue

        if choices is None:
            return answer

        answer = answer.lower()
        if answer in choices:
            return answer


def yes_no(question):
    answer = ask(question, ('y', 'n'))
    return answer == 'y'


def parse_changelog():
    all_versions = collections.OrderedDict()

    with open('changelog') as changelog_file:
        for line in changelog_file.readlines():
            line = line.rstrip()
            if not line:
                continue
            if line.startswith('Karton'):
                components = line.split(' ')
                assert components[0] == 'Karton'
                assert components[2] == '-'
                current_version = components[1]
                current_content = []
                all_versions[current_version] = current_content
            else:
                assert \
                    line.startswith('    * ') or \
                    line.startswith('      ')
                line = line[4:]
                current_content.append(line)

    for version, content_lines in all_versions.items():
        all_versions[version] = '\n'.join(content_lines)

    return all_versions


def prepare():
    # Check the docs are updated.

    tmp_docs_fileno, tmp_docs_path = tempfile.mkstemp()
    os.close(tmp_docs_fileno)

    subprocess.check_call(
        ['./scripts/props_docs.py', tmp_docs_path])

    with open(tmp_docs_path) as tmp_docs_file:
        tmp_docs_content = tmp_docs_file.read()

    with open('docs/props.md') as committed_doc_file:
        committed_doc_content = committed_doc_file.read()

    if tmp_docs_content != committed_doc_content:
        die('The documentation for props.md is outdated.\n'
            'Run "make docs" and commit the result first.')

    # Ask for the version.

    latest_version, _ = parse_changelog().items()[0]

    while True:
        version = ask('Which version do you want to release (the latest one is %s)?' %
                      latest_version)
        if yes_no('Do you really want to release version <%s>?' % version):
            break
        else:
            print()

    print()
    assert ' ' not in version

    # Change log.

    with open('changelog') as changelog_file:
        content = changelog_file.read()

    changelog_entry = CHANGELOG_ENTRY % \
        dict(
            date=datetime.datetime.now().strftime('%Y-%m-%d'),
            version=version,
            author=subprocess.check_output(['git', 'config', 'user.name']).strip(),
            email=subprocess.check_output(['git', 'config', 'user.email']).strip(),
            )

    content = changelog_entry + content

    with open('changelog', 'w') as changelog_file:
        changelog_file.write(content)

    # Version file.

    with open('karton/version.py') as version_file:
        content = version_file.read()

    content = re.sub('__version__ = \'.*\'', '__version__ = \'%s\'' % version, content)

    with open('karton/version.py', 'w') as version_file:
        version_file.write(content)

    # All done.

    print(textwrap.dedent(
        '''\
        1 - Fill the changelog file entry for version %(version)s.
        2 - Run all tests with "make distcheck".
        3 - Run "make lint".
        4 - Check everything looks fine.
        5 - Re-run this script with "push" as argument.
        ''' %
        dict(
            version=version,
            )))


def push():
    def call(*args):
        try:
            subprocess.check_call(args)
        except subprocess.CalledProcessError as exc:
            die('Couldn\'t execute command "%s": %s.' % (' '.join(args), exc))

    version, entry = parse_changelog().items()[0]
    assert 'FILL ME!' not in entry

    ask('We are going to release Karton %s!\nPress ENTER to see the diff.' % version,
        allow_empty=True)
    call('git', 'diff', 'HEAD')

    message = 'Release Karton %s' % version
    tag_name = 'v' + version

    print()
    if not yes_no('Should I commit this with message "%s" and tag "%s"?' % (message, tag_name)):
        die('Aborting release.')

    call('git', 'commit', '-a', '-m', message)

    call('git', 'tag', '--annotate', '-m', message, tag_name)

    print('\nChanges committed locally. This is your last chance to change your mind!\n')
    if not yes_no('Are you sure you want to proceed pushing release %s?' % version):
        die('Aborting release. You should revert the changes made and remove the local tag.')

    call('git', 'push', 'origin', 'master')
    call('git', 'push', 'origin', tag_name)

    release_log = 'Karton ' + version + '\n' + entry
    call('hub', 'release', 'create', '-m', release_log, tag_name)

    print(textwrap.dedent(
        '''\

        Source release for version %s made and pushed.

        Check the github link above and then push the pip release:

            python3 setup.py sdist upload -r pypi
        ''' % version))


def main(argv):
    if len(argv) != 2:
        print_help()
        raise SystemExit(1)

    all_commands = {
        'help': print_help,
        'prepare': prepare,
        'push': push,
        }

    command_name = argv[1]
    try:
        command = all_commands[command_name]
    except KeyError:
        die('Invalid command: %s' % command_name)

    command()


if __name__ == '__main__':
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        die('\n\nInterrupted.')
