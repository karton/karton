# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import subprocess

from karton import (
    pathutils,
    )

import testutils
from mixin_docker import DockerMixin
from mixin_dockerfile import DockerfileMixin
from tracked import TrackedTestCase


def bin_dir(method):
    def wrapper(self):
        tmpdir = self.make_tmp_sub_dir('bin')
        with testutils.BinPathAdder(tmpdir):
            self.session.config.alias_symlink_directory = tmpdir
            method(self)

    return wrapper


class AliasTestCase(DockerMixin,
                    DockerfileMixin,
                    TrackedTestCase):
    '''
    Test the alias command.
    '''

    _alias_name_number = 0

    @staticmethod
    def get_alias_name(main_name):
        '''
        Get a file name suitable to be used as executable name which contains `main_name`
        in it.

        The name is guaranteed not to be clashing with an existing executable name in
        `$PATH`.
        '''
        alias_name = '_karton_alias_test_%s_%d' % (main_name, AliasTestCase._alias_name_number)
        AliasTestCase._alias_name_number += 1

        for dir_path in pathutils.get_system_executable_paths():
            path = os.path.join(dir_path, alias_name)
            assert not os.path.exists(path)

        return alias_name

    def test_no_aliases(self):
        self.assertFalse(self.get_aliases())

    @bin_dir
    def test_add(self):
        image_name = self.build_fedora_latest()
        alias_name = self.get_alias_name('fedora')
        self.run_karton(['alias', alias_name, image_name])

        aliases = self.get_aliases()
        self.assert_items_equal(aliases.keys(), [alias_name])
        self.assertEqual(aliases[alias_name]['image-name'], image_name)

    @bin_dir
    def test_add_invalid(self):
        alias_name = self.get_alias_name('something')
        self.run_karton(['alias', alias_name, 'INVALID'], ignore_fail=True)
        self.assert_exit_fail()
        self.assertFalse(self.get_aliases())

    @bin_dir
    def test_add_twice_identical(self):
        image_name = self.build_fedora_latest()
        alias_name = self.get_alias_name('fedora')

        self.run_karton(['alias', alias_name, image_name])
        self.assert_items_equal(self.get_aliases().keys(), [alias_name])

        self.run_karton(['alias', alias_name, image_name], ignore_fail=True)
        self.assert_exit_fail()
        self.assert_items_equal(self.get_aliases().keys(), [alias_name])

    @bin_dir
    def test_add_twice_identical_different_implied(self):
        image_name = self.build_fedora_latest()
        alias_name = self.get_alias_name('fedora')

        self.run_karton(['alias', '--command', 'run', alias_name, image_name])
        self.assert_items_equal(self.get_aliases().keys(), [alias_name])

        self.run_karton(['alias', alias_name, image_name], ignore_fail=True)
        self.assert_exit_fail()
        self.assert_items_equal(self.get_aliases().keys(), [alias_name])
        self.assertEqual(self.get_aliases()[alias_name]['implied-command'], 'run')

    @bin_dir
    def test_add_twice_same_name_different_images(self):
        image_name1 = self.build_fedora_latest()
        image_name2 = self.build_ubuntu_latest_with_gcc()
        alias_name = self.get_alias_name('fedora')

        self.run_karton(['alias', alias_name, image_name1])
        self.assert_items_equal(self.get_aliases().keys(), [alias_name])

        self.run_karton(['alias', alias_name, image_name2], ignore_fail=True)
        self.assert_exit_fail()
        self.assert_items_equal(self.get_aliases().keys(), [alias_name])

    @bin_dir
    def test_add_two_for_same_image(self):
        image_name = self.build_fedora_latest()
        alias_name1 = self.get_alias_name('fedora')
        alias_name2 = self.get_alias_name('something-else')

        self.run_karton(['alias', alias_name1, image_name])
        self.assert_items_equal(self.get_aliases().keys(), [alias_name1])

        self.run_karton(['alias', alias_name2, image_name])
        self.assertEqual(2, len(self.get_aliases()))

    @bin_dir
    def test_add_and_remove(self):
        image_name1 = self.build_fedora_latest()
        alias_name1 = self.get_alias_name('fedora')

        image_name2 = self.build_ubuntu_latest_with_gcc()
        alias_name2 = self.get_alias_name('fedora')

        # Add one alias and remove it.
        self.run_karton(['alias', alias_name1, image_name1])
        self.assert_items_equal(self.get_aliases().keys(), [alias_name1])

        self.run_karton(['alias', '--remove', alias_name1])
        self.assertFalse(self.get_aliases())

        # Add two aliases, remove one and the remove the other.
        self.run_karton(['alias', alias_name1, image_name1])
        self.assert_items_equal(self.get_aliases().keys(), [alias_name1])

        self.run_karton(['alias', alias_name2, image_name2])
        self.assert_items_equal(self.get_aliases().keys(), [alias_name1, alias_name2])

        self.run_karton(['alias', '--remove', alias_name1])
        self.assert_items_equal(self.get_aliases().keys(), [alias_name2])

        self.run_karton(['alias', '--remove', alias_name2])
        self.assertFalse(self.get_aliases())

    @bin_dir
    def test_remove_unbuilt(self):
        def setup_image(props):
            pass

        image_name = 'an-image-which-should-not-be-built'
        import_info = self.prepare_for_image_import(setup_image)
        self.run_karton(['image', 'import', image_name, import_info.definition_dir])

        alias_name = self.get_alias_name('unbuilt')
        self.run_karton(['alias', alias_name, image_name])
        self.run_karton(['alias', '--remove', alias_name])
        self.assertFalse(self.get_aliases())

    @bin_dir
    def test_commands_work(self):
        image_name = self.build_fedora_latest()
        alias_name = self.get_alias_name('fedora')
        self.run_karton(['alias', alias_name, image_name])

        it_works = 'IT WORKS!'

        # This should fail as no image is specified.
        self.run_karton(['run', '--no-cd', 'echo', it_works], ignore_fail=True)
        self.assert_exit_fail()

        # This should fail as the alias is not valid.
        self.run_karton(['run', '--no-cd', 'echo', it_works], prog='invalid', ignore_fail=True)
        self.assert_exit_fail()

        # These should work as the image is implied.

        self.run_karton(['run', '--no-cd', 'echo', it_works], prog=alias_name)
        self.assertIn(it_works, self.current_text)

        self.spawn_karton(['run', '--no-cd', 'echo', it_works], prog=alias_name)
        self.assertIn(it_works, self.current_text)

        output = subprocess.check_output(
            [alias_name, 'run', '--no-cd', 'echo', it_works],
            universal_newlines=True)
        self.assertIn(it_works, output)

        # The alias command is not available with an implied image name.
        self.run_karton(['alias'], prog=alias_name, ignore_fail=True)
        self.assert_exit_fail()
        self.assertIn('COMMAND: invalid choice: \'alias\'', self.current_text)

    @bin_dir
    def test_implied_run_command(self):
        image_name = self.build_fedora_latest()
        alias_name = self.get_alias_name('fedora')
        self.run_karton(['alias', '--command', 'run', alias_name, image_name])

        it_works = 'IT WORKS!'

        # This shouldn't work as the command is implied, so it tries to execute
        # "run" which doesn't exists.
        self.run_karton(['run', '--no-cd', 'echo', it_works], prog=alias_name,
                        ignore_fail=True)
        self.assert_exit_fail()

        # This should work as the alias is used correctly.
        self.run_karton(['--no-cd', 'echo', it_works], prog=alias_name)
        self.assertIn(it_works, self.current_text)

    @bin_dir
    def test_implied_status_command(self):
        image_name = self.build_fedora_latest()
        alias_name = self.get_alias_name('fedora')
        self.run_karton(['alias', '--command', 'status', alias_name, image_name])

        self.run_karton([], prog=alias_name)
        self.assertIn('is not running', self.current_text)
