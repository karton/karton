# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

try:
    # Python 2.
    import ConfigParser as configparser
except ImportError:
    # Python 3.
    import configparser

import glob
import json
import os

from log import die, verbose


class ImageConfig(object):
    '''
    Configuration for a single image definition.
    '''

    def __init__(self, image_name, json_config_path):
        '''
        Initializes an ImageConfig instance.

        parser - a configparser.RawConfigParser instance for the file where the
                 image configuration is stored.
        section_name - the name of the section in the configuration file for
                       the image.
        image_name - the user-visible image name.
        '''
        verbose('Loading "%s" for image "%s".' % (json_config_path, image_name))

        self._image_name = image_name
        self._json_config_path = json_config_path

        try:
            with open(self._json_config_path, 'r') as json_file:
                self._content = json.load(json_file)
        except IOError as exc:
            die('Cannot read configuration file "%s" for image "%s": %s.' %
                (self._json_config_path, self._image_name, exc))

    def save(self):
        '''
        Save the JSON configuration file to disk.
        '''
        with open(self._json_config_path, 'w') as json_file:
            json.dump(self._content, json_file,
                      indent=4,
                      separators=(',', ': '))

    @property
    def image_name(self):
        '''
        The user-visible image name.
        '''
        return self._image_name

    @property
    def content_directory(self):
        '''
        The path to the directory where the image definition and files are stored.
        '''
        return self._content.get('content-directory')


class GlobalConfig(object):
    '''
    Read and write the Karton configuration file.
    '''

    def __init__(self, config_path):
        '''
        Initializes a GlobalConfig object.

        filename - the path for the configuration file (which doesn't need to
                   exist).
        '''
        self._config_path = config_path

        self._parser = configparser.SafeConfigParser()
        main_config_path = os.path.join(self._config_path, 'karton.cfg')
        self._parser.read([main_config_path])

        self._image_paths = None
        self._images = {}

    def _ensure_image_names_loaded(self):
        '''
        Make sure that the configuration of the images has been loaded into
        memory.
        '''
        if self._image_paths is not None:
            return

        self._image_paths = {}

        json_extension = '.json'
        for image_json_config_path in glob.glob(os.path.join(self._config_path,
                                                             'images',
                                                             '*' + json_extension)):
            image_name = os.path.basename(image_json_config_path)
            assert image_name.endswith(json_extension)
            image_name = image_name[:-len(json_extension)]

            self._image_paths[image_name] = image_json_config_path

    def image_with_name(self, image_name):
        '''
        Returns the ImageConfig instance representing the configuration of
        the image called image_name or None if the image doesn't exist.

        image_name - the name of the image
        '''
        self._ensure_image_names_loaded()

        image_json_config_path = self._image_paths.get(image_name)
        if image_json_config_path is None:
            # This image doesn't exist.
            return None

        # The image exists.
        image_config = self._images.get(image_name)

        if image_config is None:
            # But the configuration isn't loaded yet.
            image_config = ImageConfig(image_name, image_json_config_path)
            self._images[image_name] = image_config

        return image_config
