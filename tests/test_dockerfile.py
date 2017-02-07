# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import unittest

from karton import (
    dockerfile,
    )

from mixin_dockerfile import DockerfileMixin


class DockerfileTestCase(DockerfileMixin,
                         unittest.TestCase):
    '''
    Test the generation of `Dockerfile` files (but don't actually invoke Docker).
    '''

    def test_setup_nothing(self):
        def setup_image(props):
            setup_image.called = True

        setup_image.called = False

        build_info = self.make_builder(setup_image)
        self.assertTrue(os.path.isdir(build_info.dockerfile_dir))
        self.assertFalse(os.path.exists(build_info.dockerfile_path))
        self.assertFalse(setup_image.called)

        build_info.builder.generate()
        self.assertTrue(os.path.exists(build_info.dockerfile_path))
        self.assertTrue(setup_image.called)

        with open(build_info.dockerfile_path) as dockerfile_file:
            content = dockerfile_file.read()

        self.assertIn('\nFROM ubuntu:latest\n', content)
        self.assertNotIn('MAINTAINER', content)

        build_info.builder.cleanup()
        self.assertFalse(os.path.exists(build_info.dockerfile_dir))

    def test_setup_stuff(self):
        new_values = {
            'maintainer': ('myself', '\nMAINTAINER %s\n'),
            'distro': ('debian:testing', '\nFROM %s\n'),
            'username': ('anotherUser', '\nUSER %s\n'),
            'user_home': ('/home/blahBlah', '--home-dir %s '),
            'hostname': ('xyz', None),
            }

        def setup_image(props):
            self.assertEqual(props.image_name, 'new-image')

            for name, (value, _) in new_values.iteritems():
                old_value = getattr(props, name)
                self.assertNotEqual(old_value, value)

                setattr(props, name, value)

        build_info = self.make_builder(setup_image)
        build_info.builder.generate()

        with open(build_info.dockerfile_path) as dockerfile_file:
            content = dockerfile_file.read()

        for value, expected_text in new_values.itervalues():
            if expected_text is None:
                self.assertNotIn(value, content)
            else:
                expected_text = expected_text % value
                self.assertIn(expected_text, content)

    def test_distros(self):
        names = (
            'debian', 'debian:lastest', 'debian:testing', 'debian:foo',
            'ubuntu', 'ubuntu:latest', 'ubuntu:trusty',
            )
        for name in names:
            # pylint: disable=cell-var-from-loop
            def setup_image(props):
                props.distro = name

            image_name = 'new-image-' + name.replace(':', '-')
            build_info = self.make_builder(setup_image, image_name)
            build_info.builder.generate()

            with open(build_info.dockerfile_path) as dockerfile_file:
                content = dockerfile_file.read()

            self.assertIn(name, content)

    def test_error_definition_error(self):
        def setup_image(props):
            props.distro = "invalid"

        build_info = self.make_builder(setup_image)
        with self.assertRaisesRegexp(dockerfile.DefinitionError, 'Invalid distro'):
            build_info.builder.generate()

    def test_error_other(self):
        def setup_image(props):
            props.this_does_not_exist()

        build_info = self.make_builder(setup_image)
        # Normal exceptions are transformed into a DefinitionError.
        with self.assertRaises(dockerfile.DefinitionError):
            build_info.builder.generate()
