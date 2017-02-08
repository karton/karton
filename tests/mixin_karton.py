# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from karton import (
    configuration,
    log,
    karton,
    pathutils,
    runtime,
    )

import testutils


class FakeHostSystem(object):

    def __init__(self):
        self.username = 'testUser'
        self.user_home = '/foo/bar/testUserHome'
        self.hostname = 'test-host-hostname'


class KartonMixin(unittest.TestCase):
    '''
    A mixin providing basic features to run and control Karton.
    '''

    @staticmethod
    def run_and_spawn(function):
        '''
        Decorator which makes the method run twice; once it's passed `run_karton` and
        once `spawn_karton`.

        Using this, a method can test that both ways of spawning Karton work reliably.

        The decorated method is called with a single argument which is either `run_karton`
        or `spawn_karton`.

        function:
            The method to decorate.
        '''
        def call_function(self):
            function(self, self.run_karton)
            function(self, self.spawn_karton)

        return call_function

    def setUp(self):
        super(KartonMixin, self).setUp()

        self._last_exit_code = None

        # Directories.
        # The realpath is needed on OS X as Docker gets confused on whether the directory can be
        # shared if there are symlinks in it. See <https://github.com/docker/docker/issues/30738>.
        self.tmp_dir = os.path.realpath(tempfile.mkdtemp())

        self.config_dir = os.path.join(self.tmp_dir, 'config')
        os.mkdir(self.config_dir)
        os.environ['KARTON_CONFIG_DIR'] = self.config_dir

        self.session_data_dir = os.path.join(self.tmp_dir, 'data')
        os.mkdir(self.session_data_dir)

        # Session.
        self.session = runtime.Session(
            self.session_data_dir,
            FakeHostSystem(),
            configuration.GlobalConfig(runtime.Session.configuration_dir()),
            self.create_docker())

    def tearDown(self):
        super(KartonMixin, self).tearDown()

        shutil.rmtree(self.tmp_dir)

    @property
    def docker(self):
        return self.session.docker

    def create_docker(self):
        return self

    def make_tmp_sub_dir(self, intermediate=None):
        '''
        Create a directory inside this test's temporary directory.

        intermediate:
            If not None, the new directory will be a sub directory of intermediate
            which will be a subdirectory of the tests' temporary directory.
        Return value:
            The path to an existing empty temporary directory.
        '''
        if intermediate is None:
            base_dir = self.tmp_dir
        else:
            base_dir = os.path.join(self.tmp_dir, intermediate)
            pathutils.makedirs(base_dir)

        return tempfile.mkdtemp(dir=base_dir)

    @property
    def current_text_as_lines(self):
        '''
        The output of the latest Karton invokation split into lines.

        Return value:
            A list of strings representing the output of Karton.
        '''
        text = self.current_text.strip()
        return [line for line in text.split('\n') if line.strip()]

    @property
    def deserialized_current_text(self):
        '''
        The output of the latest Karton invokation parsed as JSON and converted to an object.

        Return value:
            An object representing the JSON output of Karton.
        '''
        return json.loads(self.current_text)

    def run_karton(self, arguments, prog=None, ignore_fail=False):
        '''
        Run Karton as a module.

        The output from Karton is saved in `current_text` after Karton terminates.

        arguments:
            The arguments to pass to Karton (excluding argument 0, i.e. the program name).
        prog:
            The name of the Karton program (i.e. what would be `sys.argv[0]`) or `None` to default
            to Karton.
        ignore_fail:
            If false, errors cause an assertion failure.
            If true, errors are ignored.
        '''
        if prog is None:
            prog = 'karton'

        self._last_exit_code = 0
        self.current_text = 'INVALID'

        try:
            try:
                redirector = testutils.Redirector()
                try:
                    with redirector:
                        karton.run_karton(self.session, [prog] + arguments)
                finally:
                    self.current_text = redirector.content

            except log.ExitDueToFailure as exc:
                self._last_exit_code = exc.code
                if not ignore_fail:
                    self.fail('Karton failed unexpectedly (ExitDueToFailure exception): %s' % exc)
            except SystemExit as exc:
                self._last_exit_code = exc.code
                if not ignore_fail and self._last_exit_code != 0:
                    self.fail('Karton failed unexpectedly, exit code is %d '
                              '(even if ExitDueToFailure was not raised)' % self._last_exit_code)
        except Exception:
            if self._last_exit_code == 0:
                self._last_exit_code = 1

            if self.current_text.strip():
                sys.stderr.write(
                    '\n'
                    'The output from the failing Karton invokation is:\n'
                    '================\n'
                    '%s\n'
                    '================\n' %
                    self.current_text.strip())
            raise

        return self._last_exit_code

    def spawn_karton(self, arguments, prog=None, ignore_fail=False):
        '''
        Run Karton as a separate process.

        This is less flexible than using `run_karton`, but is heplful to test that Karton can
        be actually spawned.

        The output from Karton is saved in `current_text` after Karton terminates.

        arguments:
            The arguments to pass to Karton (excluding argument 0, i.e. the program name).
        prog:
            The name of the Karton program (i.e. what would be `sys.argv[0]`) or `None` to default
            to Karton.
        ignore_fail:
            If false, errors cause an assertion failure.
            If true, errors are ignored.
        '''
        if prog is None:
            prog = karton.__file__

        self._last_exit_code = 0
        self.current_text = 'INVALID'

        redirector = testutils.Redirector()
        try:
            with redirector:
                self._last_exit_code = subprocess.call(['python', prog] + arguments)
        except KeyboardInterrupt:
            if redirector.content.strip():
                sys.stderr.write(
                    '\n'
                    'The output from the failing Karton invokation is:\n'
                    '================\n'
                    '%s\n'
                    '================\n' %
                    redirector.content.strip())
            raise
        finally:
            self.current_text = redirector.content

        if not ignore_fail and self._last_exit_code != 0:
            self.fail('Karton invokation failed with exit code %d' % self._last_exit_code)

        return self._last_exit_code

    def get_aliases(self):
        '''
        Get the currently configured aliases.

        Return value:
            A JSON-based dictionary representation of the available aliases.
        '''
        self.run_karton(['alias', '--json'])
        return self.deserialized_current_text

    def get_status(self, image_name):
        '''
        Get the status of an image.

        image_name:
            The name of the image to query.
        Return value:
            A JSON-based dictionary representation of the status.
        '''
        self.run_karton(['status', '--json', image_name])
        return self.deserialized_current_text

    def get_images(self):
        '''
        List all available images.

        Return value:
            A JSON-based dictionary listing all available images.
        '''
        self.run_karton(['image', 'list', '--json'])
        return self.deserialized_current_text

    def assert_exit_success(self):
        '''
        Assert that the latest invokation of Karton terminated with a 0 exit code.
        '''
        if self._last_exit_code is None:
            self.fail('assert_exit_success called before running Karton')

        self.assertEqual(self._last_exit_code, 0,
                         'Karton was expected to have succeeded, but it didn\'t')

    def assert_exit_fail(self):
        '''
        Assert that the latest invokation of Karton terminated with a non-0 exit code.
        '''
        if self._last_exit_code is None:
            self.fail('assert_exit_fail called before running Karton')

        self.assertNotEqual(self._last_exit_code, 0,
                            'Karton was expected to have failed, but it didn\'t')
