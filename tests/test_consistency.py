# Copyright (C) 2018 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import sys

from mixin_fake_docker import FakeDockerMixin
from tracked import TrackedTestCase


class ConsistencyTestCase(FakeDockerMixin,
                          TrackedTestCase):
    '''
    Test that consistency controls work well.
    '''

    def setUp(self):
        super(ConsistencyTestCase, self).setUp()

        self.shared_host_path = self.make_tmp_sub_dir('dir-to-share')
        self.shared_image_path = '/shared'

    def make_image(self, setup_image):
        '''
        Add an image to Karton *without* calling docker.
        '''
        image_name = 'test-dummy-image'
        import_info = self.prepare_for_image_import(setup_image)
        self.run_karton(['image', 'import', image_name, import_info.definition_dir])

        self.run_karton(['build', image_name])

        return image_name

    def run_true(self, image_name):
        '''
        Run the `true` program and returns the command line passed to Docker (as
        a list of strings).
        '''
        self.run_karton(['run', '--no-cd', image_name, 'true'])
        return self.get_last_command('run')

    def verify_path(self, setup_image, expected_consistency):
        '''
        Configure a new image using `setup_image`, shares `self.shared_host_path` as
        `self.shared_image_path` with `expected_consistency` as consistency, and
        verifies that the correct command line arguments are passed to Docker.
        '''
        image_name = self.make_image(setup_image)
        args = self.run_true(image_name)

        expected = '%s:%s' % (self.shared_host_path, self.shared_image_path)
        if sys.platform == 'darwin':
            expected += ':' + expected_consistency

        self.assertIn(expected, args)

        mount_index = args.index(expected)
        self.assertTrue(mount_index >= 1)

        self.assertEqual(args[mount_index - 1], '-v')

    def test_default_unchanged(self):
        def setup_image(props):
            props.share_path(self.shared_host_path, self.shared_image_path)

        self.verify_path(setup_image, 'consistent')

    def test_default_changed(self):
        def setup_image(props):
            props.default_consistency = props.CONSISTENCY_CACHED
            props.share_path(self.shared_host_path, self.shared_image_path)

        self.verify_path(setup_image, 'cached')

    def test_default_overwritten_by_path(self):
        def setup_image(props):
            props.default_consistency = props.CONSISTENCY_DELEGATED
            props.share_path(self.shared_host_path, self.shared_image_path,
                             props.CONSISTENCY_CACHED)

        self.verify_path(setup_image, 'cached')

    def test_specified_in_path(self):
        def setup_image(props):
            props.share_path(self.shared_host_path, self.shared_image_path,
                             props.CONSISTENCY_DELEGATED)

        self.verify_path(setup_image, 'delegated')

    def test_specified_as_none(self):
        def setup_image(props):
            props.default_consistency = props.CONSISTENCY_DELEGATED
            props.share_path(self.shared_host_path, self.shared_image_path,
                             None)

        self.verify_path(setup_image, 'delegated')
