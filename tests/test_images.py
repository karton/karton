# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os

from mixin_dockerfile import DockerfileMixin
from tracked import TrackedTestCase


class ImagesTestCase(DockerfileMixin,
                     TrackedTestCase):
    '''
    Test commands which manipulate images.
    '''

    def __init__(self, *args, **kwargs):
        super(ImagesTestCase, self).__init__(*args, **kwargs)

        self._image_we_are_removing = None

    def test_image_create(self, number_images_before=0):
        create_info = self.prepare_for_image_create()
        self.assertTrue(os.path.isdir(create_info.definition_parent_dir))
        self.assertFalse(os.path.exists(create_info.future_definition_dir))
        self.assertFalse(os.path.exists(create_info.future_definition_path))

        image_name = 'an-image-' + str(number_images_before)

        images = self.get_images()
        self.assertEqual(len(images), number_images_before)
        self.assertNotIn(image_name, images)

        self.run_karton(['image', 'create', image_name, create_info.future_definition_dir])
        self.assert_exit_success()
        self.assertTrue(os.path.isfile(create_info.future_definition_path))

        with open(create_info.future_definition_path) as definition_file:
            content = definition_file.read()

        self.assertIn('def setup_image(props):\n', content)

        images = self.get_images()
        self.assertEqual(len(images), number_images_before + 1)
        self.assertIn(image_name, images)

        status = self.get_status(image_name)
        self.assertFalse(status['running'])

        return image_name

    def test_image_import(self, number_images_before=0):
        def setup_image(props):
            self.fail('This setup_image should never be called.')

        import_info = self.prepare_for_image_import(setup_image)
        self.assertTrue(os.path.isdir(import_info.definition_dir))
        self.assertTrue(os.path.isfile(import_info.definition_path))
        self.assertTrue(import_info.definition_path.startswith(import_info.definition_dir))

        def get_definition_content():
            with open(import_info.definition_path) as definition_file:
                return definition_file.read()

        image_name = 'an-image-' + str(number_images_before)

        images = self.get_images()
        self.assertEqual(len(images), number_images_before)
        self.assertNotIn(image_name, images)

        old_content = get_definition_content()
        self.run_karton(['image', 'import', image_name, import_info.definition_dir])
        self.assert_exit_success()
        new_content = get_definition_content()
        self.assertEqual(old_content, new_content) # Import shouldn't modify the file.

        images = self.get_images()
        self.assertEqual(len(images), number_images_before + 1)
        self.assertIn(image_name, images)

        status = self.get_status(image_name)
        self.assertFalse(status['running'])

        return image_name

    def test_add_multiple(self):
        self.test_image_create(0)
        self.test_image_create(1)
        self.test_image_import(2)
        self.test_image_import(3)
        self.test_image_create(4)

    def test_image_list(self):
        # No images.
        self.run_karton(['image', 'list'])
        self.assertIn('No images configured.', self.current_text)
        self.assertEqual(len(self.current_text_as_lines), 1)

        # One image.
        image0 = self.test_image_create(0)
        self.run_karton(['image', 'list'])
        self.assertIn(' - %s at "%s' % (image0, self.tmp_dir), self.current_text)
        self.assertEqual(len(self.current_text_as_lines), 1)

        # Two images.
        image1 = self.test_image_create(1)
        self.run_karton(['image', 'list'])
        self.assertIn(' - %s at "%s' % (image0, self.tmp_dir), self.current_text)
        self.assertIn(' - %s at "%s' % (image1, self.tmp_dir), self.current_text)
        self.assertEqual(len(self.current_text_as_lines), 2)

    def check_output(self, arguments):
        self.assertEqual(len(arguments), 3)
        self.assertEqual(arguments[0], 'rmi')
        self.assertEqual(arguments[1], '--force')
        self.assertEqual(arguments[2], self._image_we_are_removing)
        return 'INVALID'

    def test_image_remove(self):
        # No images.
        images = self.get_images()
        self.assertEqual(len(images), 0)

        # Add one image.
        image0 = self.test_image_create(0)

        images = self.get_images()
        self.assertEqual(len(images), 1)
        self.assertIn(image0, images)

        # Add another image.
        image1 = self.test_image_create(1)

        images = self.get_images()
        self.assertEqual(len(images), 2)
        self.assertIn(image0, images)
        self.assertIn(image1, images)

        # Remove the latest image.
        self._image_we_are_removing = image1
        self.run_karton(['image', 'remove', image1])

        images = self.get_images()
        self.assertEqual(len(images), 1)
        self.assertIn(image0, images)
        self.assertNotIn(image1, images)

        # Add another image.
        image1 = self.test_image_create(1)

        images = self.get_images()
        self.assertEqual(len(images), 2)
        self.assertIn(image0, images)
        self.assertIn(image1, images)

        # Remove both images.
        self._image_we_are_removing = image1
        self.run_karton(['image', 'remove', image1])

        self._image_we_are_removing = image0
        self.run_karton(['image', 'remove', image0])

        images = self.get_images()
        self.assertEqual(len(images), 0)
