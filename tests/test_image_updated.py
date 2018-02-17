# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from karton import (
    version,
    )

from mixin_docker import DockerMixin
from mixin_dockerfile import DockerfileMixin
from testutils import OverwriteVersion
from tracked import TrackedTestCase


class TestImageUpdated(DockerMixin,
                       DockerfileMixin,
                       TrackedTestCase):
    '''
    Test the we detect correctly if we are trying to run against an outdated image.
    '''

    command_text = 'This is the command\'s output'

    def run_echo(self, image_name):
        self.run_karton(['run', '--no-cd', image_name, 'echo', self.command_text],
                        ignore_fail=True)

    def test_start_time(self):
        image_name = self.build_ubuntu_latest_with_gcc()

        self.assert_not_running(image_name)
        self.run_echo(image_name)
        self.assertEqual(self.current_text.strip(), self.command_text)
        self.assert_running(image_name)

        self.forget_cached_props(image_name)
        self.run_karton(['build', image_name])
        self.run_echo(image_name)
        # The command did run, but there should be a warning as well.
        self.assertIn(self.command_text, self.current_text)
        self.assertIn('was re-built after the currently running image was started',
                      self.current_text)

        self.run_karton(['stop', image_name])
        self.assert_not_running(image_name)
        self.run_echo(image_name)
        # Only the expected output and nothing else.
        self.assertEqual(self.current_text.strip(), self.command_text)

    def test_built_with_version(self):
        image_name = self.build_ubuntu_latest_with_gcc()

        self.assert_not_running(image_name)
        self.run_echo(image_name)
        self.assertEqual(self.current_text.strip(), self.command_text)

        real_version = version.numeric_version

        new_version = list(real_version)
        new_version[-1] += 1
        new_version = tuple(new_version)

        old_version = (0, 0, 1)

        for overwrite in (new_version, real_version, old_version, real_version):
            with OverwriteVersion(overwrite):
                def check_failed(overwrite=overwrite):
                    self.assertIn('was built with Karton', self.current_text)
                    # overwrite could as well be the same as real_version here, but it
                    # doesn't matter.
                    self.assertIn(OverwriteVersion.version_as_text(overwrite),
                                  self.current_text)
                    self.assertIn(OverwriteVersion.version_as_text(real_version),
                                  self.current_text)
                    self.assertNotIn(self.command_text, self.current_text)

                self.assert_running(image_name)
                self.run_echo(image_name)
                check_failed()

                self.run_karton(['stop', image_name])
                self.assert_not_running(image_name)

                self.run_karton(['start', image_name], ignore_fail=True)
                check_failed()
                self.assert_not_running(image_name)

                self.forget_cached_props(image_name)
                self.run_karton(['build', image_name])
                self.run_echo(image_name)
                self.assertEqual(self.current_text.strip(), self.command_text)
