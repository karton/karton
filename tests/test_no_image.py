# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import unittest

from mixin_karton import KartonMixin


class NoImageTestCase(KartonMixin,
                      unittest.TestCase):
    '''
    Test commands which don't require images to exist or Docker to be invoked.
    '''

    def _verify_help_message(self):
        self.assertIn('usage: karton ', self.current_text)
        self.assertIn('positional arguments:', self.current_text)
        self.assertIn('optional arguments:', self.current_text)

    @KartonMixin.run_and_spawn
    def test_no_args(self, run_or_spawn):
        run_or_spawn([], ignore_fail=True)
        self.assert_exit_fail()
        self._verify_help_message()

    @KartonMixin.run_and_spawn
    def test_help(self, run_or_spawn):
        run_or_spawn(['help'])
        self.assert_exit_success()
        self._verify_help_message()

    @KartonMixin.run_and_spawn
    def test_incomplete_commands(self, run_or_spawn):
        for cmd in ('run', 'shell', 'start', 'stop', 'status', 'build', 'image',
                    'image create', 'image import'):
            run_or_spawn(cmd.split(' '), ignore_fail=True)
            self._verify_help_message()
            self.assert_exit_fail()

    @KartonMixin.run_and_spawn
    def test_alias_query(self, run_or_spawn):
        run_or_spawn(['alias'])
        self.assert_exit_success()
        self.assertEqual('', self.current_text)

        run_or_spawn(['alias', 'invalid'], ignore_fail=True)
        self.assert_exit_fail()
        self.assertIn('"invalid" is not a known alias.', self.current_text)

        run_or_spawn(['alias', 'invalid', 'not-an-image'], ignore_fail=True)
        self.assert_exit_fail()
        self.assertIn('Cannot add alias "invalid" for image "not-an-image" as the image does '
                      'not exist.',
                      self.current_text)

    @KartonMixin.run_and_spawn
    def test_run_with_invalid_image(self, run_or_spawn):
        for cmd in ('run', 'shell', 'start', 'stop', 'status', 'build'):
            run_or_spawn([cmd, 'not-an-image'], ignore_fail=True)
            self.assert_exit_fail()
            self.assertIn('The image "not-an-image" doesn\'t exist.', self.current_text)

    @KartonMixin.run_and_spawn
    def test_no_images(self, run_or_spawn):
        run_or_spawn(['image', 'list'])
        self.assert_exit_success()
        self.assertIn('No images configured.', self.current_text)
