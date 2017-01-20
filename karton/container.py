# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import tempfile

import dockerfile
import pathutils

from log import die


class Image(object):
    '''
    A Karton image.
    '''

    def __init__(self, session, image_config):
        '''
        Initializes an Image instance.

        All the methods starting with "command_" deal with expected exceptions
        (by calling log.die if needed) and are suitable to be called by a command
        line tool. If you want to handle the exceptions by yourself, call the
        method version not prefixed by "command_".

        session - a runtime.Session.
        image_config - a configuration.ImageConfig to configure the image.
        '''
        self._session = session
        self._image_config = image_config

    def command_build(self):
        '''
        Build the image.
        '''
        try:
            self.build()
        except dockerfile.DefinitionError as exc:
            die(str(exc))

    def build(self):
        dest_path_base = os.path.join(self._session.data_dir, 'builder')
        pathutils.makedirs(dest_path_base)
        dest_path = tempfile.mkdtemp(prefix=self._image_config.image_name + '-',
                                     dir=dest_path_base)

        builder = dockerfile.Builder(self._image_config.image_name,
                                     self._image_config.path,
                                     dest_path,
                                     self._session.host_system)

        try:
            builder.generate()

            self._session.docker.call(
                ['build', '--tag', self._image_config.image_name, dest_path])

        finally:
            builder.cleanup()
