# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import collections
import os
import sys

from karton import (
    dockerfile,
    pathutils,
    )

from mixin_karton import KartonMixin


PROXY_DEFINITION_CONTENT = '''\
def setup_image(props):
    import shared_definition_stuff
    shared_definition_stuff.setup_image(props)
'''


ImageCreateInfo = collections.namedtuple(
    'ImageCreateInfo',
    ['definition_parent_dir', 'future_definition_dir', 'future_definition_path'])


ImageImportInfo = collections.namedtuple(
    'ImageImportInfo',
    ['definition_dir', 'definition_path'])


DockerfileBuildInfoBase = collections.namedtuple(
    'DockerfileBuildInfo',
    ['builder', 'dockerfile_dir', 'dockerfile_path'])


class DockerfileBuildInfo(DockerfileBuildInfoBase):

    def read_content(self):
        '''
        Read the content of the Dockerfile.

        Return value:
            A string with the Dockerfile content.
        '''
        with open(self.dockerfile_path) as dockerfile_file:
            return dockerfile_file.read()


class FakeDefinitionModule(object):

    def __init__(self, setup_image):
        self.setup_image = setup_image


class DockerfileMixin(KartonMixin):
    '''
    A mixin used for tests which needs to generate `Dockerfile` files.
    '''

    @staticmethod
    def _create_definition(definition_dir, setup_image_callback):
        '''
        Create a definition file, which will call `setup_image_callback`.

        definition_dir:
            The path of the directory where to create the definition file.
        setup_image_callback:
            A function to call to setup a `DefinitionProperties`.
        '''
        sys.modules['shared_definition_stuff'] = FakeDefinitionModule(setup_image_callback)

        definition_path = os.path.join(definition_dir, 'definition.py')
        with open(definition_path, 'w') as definition_file:
            definition_file.write(PROXY_DEFINITION_CONTENT)

        return definition_path

    def make_builder(self, setup_image_callback, image_name='new-image'):
        '''
        Add an image and create a `dockerfile.Builder` for a new image.

        setup_image_callback:
            A function to call to setup a `DefinitionProperties`.
        image_name:
            The name of the image to create.
        Return value:
            A `DockerfileBuildInfo` for the `dockerfile.Builder`.
        '''
        definition_dir = self.make_tmp_sub_dir('definitions')
        dockerfile_dir = self.make_tmp_sub_dir('dockerfiles')

        self._create_definition(definition_dir, setup_image_callback)

        image_config = self.session.config.add_image(image_name, definition_dir)

        return DockerfileBuildInfo(
            builder=dockerfile.Builder(image_config, dockerfile_dir, self.session.host_system),
            dockerfile_dir=dockerfile_dir,
            dockerfile_path=os.path.join(dockerfile_dir, 'Dockerfile'))

    def prepare_for_image_create(self):
        '''
        Helper to create the files needed for an `image create` command.

        Return value:
            An `ImageCreateInfo` instance.
        '''
        definition_parent_dir = self.make_tmp_sub_dir('images')
        future_definition_dir = os.path.join(definition_parent_dir, 'actual-image')

        return ImageCreateInfo(
            definition_parent_dir=definition_parent_dir,
            future_definition_dir=future_definition_dir,
            future_definition_path=os.path.join(future_definition_dir, 'definition.py'))

    def prepare_for_image_import(self, setup_image_callback):
        '''
        Helper to create the files needed for an `image import` command.

        setup_image_callback:
            A function to call to setup a `DefinitionProperties`.
        Return value:
            An `ImageImportInfo` instance.
        '''
        create_info = self.prepare_for_image_create()
        pathutils.makedirs(create_info.future_definition_dir)

        definition_path = self._create_definition(create_info.future_definition_dir,
                                                  setup_image_callback)

        return ImageImportInfo(
            definition_dir=create_info.future_definition_dir,
            definition_path=definition_path)
