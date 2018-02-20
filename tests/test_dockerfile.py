# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import textwrap

from karton import (
    defprops,
    )

from mixin_dockerfile import DockerfileMixin
from tracked import TrackedTestCase


class DockerfileTestCase(DockerfileMixin,
                         TrackedTestCase):
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

        content = build_info.read_content()
        self.assertIn('\nFROM ubuntu:latest\n', content)
        self.assertNotIn('MAINTAINER', content)

        build_info.builder.cleanup()
        self.assertFalse(os.path.exists(build_info.dockerfile_dir))

    def test_setup_stuff(self):
        new_values = {
            'maintainer': ('myself', '\nMAINTAINER %s\n'),
            'distro': ('debian:testing', '\nFROM %s\n'),
            'username': ('anotherUser', '\nUSER %s\n'),
            'uid': (666, '--uid %s '),
            'user_home': ('/home/blahBlah', '--home-dir %s '),
            'hostname': ('xyz', None),
            }

        def setup_image(props):
            self.assertEqual(props.image_name, 'new-image')

            for name, (value, _) in new_values.items():
                old_value = getattr(props, name)
                self.assertNotEqual(old_value, value)

                setattr(props, name, value)

        build_info = self.make_builder(setup_image)
        build_info.builder.generate()
        content = build_info.read_content()

        for value, expected_text in new_values.values():
            if expected_text is None:
                self.assertNotIn(value, content)
            else:
                expected_text = expected_text % value
                self.assertIn(expected_text, content)

    def test_distros(self):
        names = (
            'debian', 'debian:lastest', 'debian:testing', 'debian:foo',
            'ubuntu', 'ubuntu:latest', 'ubuntu:trusty',
            'fedora', 'fedora:lastest', 'fedora:25',
            'centos', 'centos:latest', 'centos:6',
            )
        for name in names:
            # pylint: disable=cell-var-from-loop
            def setup_image(props):
                props.distro = name

            image_name = 'new-image-' + name.replace(':', '-')
            build_info = self.make_builder(setup_image, image_name)
            build_info.builder.generate()

            content = build_info.read_content()
            self.assertIn(name, content)

    def test_error_definition_error(self):
        def setup_image(props):
            props.distro = "invalid"

        build_info = self.make_builder(setup_image)
        with self.assert_raises_regex(defprops.DefinitionError, 'Invalid distro'):
            build_info.builder.generate()

    def test_error_other(self):
        def setup_image(props):
            props.this_does_not_exist()

        build_info = self.make_builder(setup_image)
        # Normal exceptions are transformed into a DefinitionError.
        with self.assertRaises(defprops.DefinitionError):
            build_info.builder.generate()

    def _test_import(self, make_relative):
        # This definition is meant to be imported from another, so we check that the
        # values propagate and are overwritten correctly.
        inner_definition_dir = self.make_tmp_sub_dir('definitions')
        with open(os.path.join(inner_definition_dir, 'definition.py'), 'w') as inner_content:
            inner_content.write(textwrap.dedent('''\
                def setup_image(props):
                    assert props.distro == 'fedora:outer1'
                    assert props.username == 'outer-user'
                    assert props.packages == ['PACKAGE-A']

                    props.distro = 'fedora:inner'
                    props.username = 'inner-user'
                    props.packages.append('PACKAGE-B')
                '''))

        def setup_outer(props):
            props.username = 'outer-user'
            props.distro = 'fedora:outer1'
            props.packages.append('PACKAGE-A')

            if make_relative:
                inner_definition_dir_to_import = os.path.relpath(
                    inner_definition_dir,
                    os.path.dirname(props.definition_file_path))
            else:
                inner_definition_dir_to_import = inner_definition_dir

            props.import_definition(inner_definition_dir_to_import)

            props.distro = 'fedora:outer2'
            props.packages.append('PACKAGE-C')

        build_info = self.make_builder(setup_outer)
        build_info.builder.generate()
        content = build_info.read_content()

        self.assertIn('inner-user', content)
        self.assertNotIn('outer-user', content)

        self.assertIn('fedora:outer2', content)
        self.assertNotIn('fedora:outer1', content)
        self.assertNotIn('fedora:inner', content)

        self.assertIn('PACKAGE-A', content)
        self.assertIn('PACKAGE-B', content)
        self.assertIn('PACKAGE-C', content)

    def test_import_absolute(self):
        self._test_import(make_relative=False)

    def test_import_relative(self):
        self._test_import(make_relative=True)

    def test_consistency(self):
        def setup_image_default(props):
            pass

        def setup_image_cached(props):
            props.consistency = props.CONSISTENCY_CACHED

        def get_content(setup_image):
            build_info = self.make_builder(setup_image, 'new-image-' + setup_image.__name__)
            build_info.builder.generate()
            return build_info.read_content()

        # The different consistency should not affect the Dockerfile as it's
        # passed to the docker run command with -v.
        self.assertEqual(get_content(setup_image_default),
                         get_content(setup_image_cached))

    def test_setup_wrong_share_home(self):
        def setup_share_path(props):
            props.share_path(self.session.host_system.user_home)

        def setup_share_empty_path_in_home(props):
            props.share_path_in_home('')

        def setup_share_dot_path_in_home(props):
            props.share_path_in_home('.')

        def setup_share_2dots_path_in_home(props):
            props.share_path_in_home('foo/..')

        def setup_set_home_path_on_host(props):
            props.image_home_path_on_host = self.session.host_system.user_home

        all_setups = (
            setup_share_path,
            setup_share_empty_path_in_home,
            setup_share_dot_path_in_home,
            setup_share_2dots_path_in_home,
            setup_set_home_path_on_host,
            )

        for setup_image in all_setups:
            build_info = self.make_builder(setup_image, 'new-image-' + setup_image.__name__)
            with self.assert_raises_regex(defprops.DefinitionError,
                                          'The home directory can only be shared by using'):
                build_info.builder.generate()

    def test_setup_correct_share_home(self):
        def setup_image(props):
            self.assertFalse(props.share_whole_home)

            self.assertNotEqual(props.image_home_path_on_host, self.session.host_system.user_home)
            props.share_whole_home = True
            self.assertEqual(props.image_home_path_on_host, self.session.host_system.user_home)

            # We do it again to check this doesn't break (as changing the value after setting it to
            # True doesn't work, but settting to the same value should be fine).
            props.share_whole_home = True
            self.assertEqual(props.image_home_path_on_host, self.session.host_system.user_home)

        build_info = self.make_builder(setup_image)
        build_info.builder.generate()

    def test_reset_share_whole_home(self):
        def setup_image(props):
            props.share_whole_home = True
            props.share_whole_home = False

        build_info = self.make_builder(setup_image)
        with self.assert_raises_regex(defprops.DefinitionError,
                                      'Cannot reset shared_whole_home after setting it'):
            build_info.builder.generate()

    def test_run_at_build_commands(self):
        run_times = (
            defprops.DefinitionProperties.RUN_AT_BUILD_START,
            defprops.DefinitionProperties.RUN_AT_BUILD_BEFORE_USER_PKGS,
            defprops.DefinitionProperties.RUN_AT_BUILD_END,
            )

        def make_run_string(when, i):
            return 'RUNNING-%d-AT-%s' % (i, when)

        def setup_image(props):
            for i, when in enumerate(run_times):
                self.assertEqual(len(props.commands_to_run(when)), 0)
                props.run_command(when, make_run_string(when, i))
                self.assertEqual(len(props.commands_to_run(when)), 1)

        build_info = self.make_builder(setup_image)
        build_info.builder.generate()
        content = build_info.read_content()

        last_index = -1
        for i, when  in enumerate(run_times):
            run_string = make_run_string(when, i)

            self.assertIn(run_string, content)

            index = content.find(run_string)
            self.assertTrue(index > last_index)

            last_index = index

    def test_run_non_at_build_commands(self):
        # These commands shouldn't affect the Dockerfile.
        run_times = (
            defprops.DefinitionProperties.RUN_AT_START,
            defprops.DefinitionProperties.RUN_BEFORE_COMMAND,
            defprops.DefinitionProperties.RUN_AFTER_COMMAND,
            defprops.DefinitionProperties.RUN_AT_STOP,
            )

        def setup_empty_image(props):
            pass

        def setup_image_with_commands(props):
            for when in run_times:
                self.assertEqual(len(props.commands_to_run(when)), 0)
                props.run_command(when, when)
                self.assertEqual(len(props.commands_to_run(when)), 1)

        def get_content(setup_image):
            build_info = self.make_builder(setup_image, 'new-image-' + setup_image.__name__)
            build_info.builder.generate()
            return build_info.read_content()

        self.assertEqual(get_content(setup_empty_image),
                         get_content(setup_image_with_commands))
