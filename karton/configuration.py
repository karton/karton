# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

try:
    # Python 2.
    import ConfigParser as configparser
except ImportError:
    # Python 3.
    import configparser

import os

from log import info


class ImageConfig(object):
    '''
    Configuration for a single image definition.
    '''

    def __init__(self, parser, section_name, image_name):
        '''
        Initializes an ImageConfig instance.

        parser - a configparser.RawConfigParser instance for the file where the
                 image configuration is stored.
        section_name - the name of the section in the configuration file for
                       the image.
        image_name - the user-visible image name.
        '''
        self._parser = parser
        self._section_name = section_name
        self._image_name = image_name

        if not self.path:
            raise ValueError('Missing "path" value for image "%s".' % (self._image_name))

    @property
    def image_name(self):
        '''
        The user-visible image name.
        '''
        return self._image_name

    @property
    def path(self):
        '''
        The path to the dictory where the image definition and files are stored.
        '''
        return self._parser.get(self._section_name, 'path')

    @property
    def definition_file(self):
        '''
        The path to the definition file (which defines what the image contains
        and how it's built).
        '''
        return os.path.join(self.path, 'definition.py')


class GlobalConfig(object):
    '''
    Read and write the Karton configuration file.
    '''

    def __init__(self, filename):
        '''
        Initializes a GlobalConfig object.

        filename - the path for the configuration file (which doesn't need to
                   exist).
        '''
        self._filename = filename

        self._parser = configparser.SafeConfigParser()
        self._parser.read([filename])

        self._images = None

    def _ensure_images_loaded(self):
        '''
        Make sure that the configuration of the images has been loaded into
        memory.
        '''
        if self._images is not None:
            return

        self._images = {}
        image_identifier = 'image:'

        for section in self._parser.sections():
            if section == 'general':
                pass
            elif section.startswith(image_identifier):
                try:
                    image_name = section[len(image_identifier):]
                    image = ImageConfig(self._parser, section, image_name)
                    self._images[image_name] = image
                except ValueError as exc:
                    info('Invalid image definition: %s' % exc.message)
            else:
                info('Invalid section "%s" in configuration file "%s" will be ignored.' % \
                        (section, self._filename))

    def image_with_name(self, image_name):
        '''
        Returns the ImageConfig instance representing the configuration of
        the image called image_name or None if the image doesn't exist.

        image_name - the name of the image
        '''
        self._ensure_images_loaded()
        return self._images.get(image_name)
