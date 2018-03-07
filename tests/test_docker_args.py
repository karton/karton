# Copyright (C) 2018 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

from mixin_fake_docker import FakeDockerMixin
from tracked import TrackedTestCase


class DockerArgsTestCase(FakeDockerMixin,
                         TrackedTestCase):
    '''
    Test that arguments passed to Docker make sense.
    '''

    def import_image(self):
        '''
        Add an image to Karton *without* calling docker.
        '''
        def setup_image(props):
            pass

        image_name = 'test-dummy-image'
        import_info = self.prepare_for_image_import(setup_image)
        self.run_karton(['image', 'import', image_name, import_info.definition_dir])

        return image_name

    def test_cache(self):
        image_name = self.import_image()
        self.run_karton(['build', image_name])
        self.assertNotIn('--no-cache', self.get_last_command('build'))

    def test_no_cache(self):
        image_name = self.import_image()
        self.run_karton(['build', '--no-cache', image_name])
        self.assertIn('--no-cache', self.get_last_command('build'))
