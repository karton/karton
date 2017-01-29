# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

try:
    # Python 2.
    import ConfigParser as configparser
except ImportError:
    # Python 3.
    import configparser

import collections
import glob
import json
import os

from log import die, verbose


ImageAlias = collections.namedtuple('ImageAlias', ['alias_name', 'image_name', 'run'])


class ImageConfig(object):
    '''
    Configuration for a single image definition.
    '''

    def __init__(self, image_name, json_config_path, expect_existing=True):
        '''
        Initializes an ImageConfig instance.

        image_name - the user-visible image name.
        json_config_path - the path to the JSON configuration file for the image.
        expect_existing - if True, an exception will be raised if the file does not exist already;
                          if False, the non-existance of the file will be ignore, useful when
                          creating a new image.
        '''
        verbose('Loading "%s" for image "%s".' % (json_config_path, image_name))

        self._image_name = image_name
        self._json_config_path = json_config_path

        try:
            with open(self._json_config_path, 'r') as json_file:
                self._content = json.load(json_file)
        except IOError as exc:
            if expect_existing:
                die('Cannot read configuration file "%s" for image "%s": %s.' %
                    (self._json_config_path, self._image_name, exc))
            else:
                self._content = {}

    def save(self):
        '''
        Save the JSON configuration file to disk.
        '''
        assert self.content_directory

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

    @content_directory.setter
    def content_directory(self, content_directory):
        self._content['content-directory'] = content_directory

    @property
    def shared_paths(self):
        '''
        A sequence of two-items tuples representing the directories or files shared between
        host and container.

        The first tuple element is the path on the host, the second one is the path in the
        container.
        '''
        return tuple(self._content.get('shared-paths', ()))

    @shared_paths.setter
    def shared_paths(self, paths):
        self._content['shared-paths'] = paths

    @property
    def hostname(self):
        '''
        The image hostname.
        '''
        return self._content.get('hostname', 'missing-hostname-in-configuration')

    @hostname.setter
    def hostname(self, hostname):
        self._content['hostname'] = hostname

    @property
    def user_home(self):
        '''
        The home directory of the main user.
        '''
        return self._content.get('user-home', '/')

    @user_home.setter
    def user_home(self, user_home):
        self._content['user-home'] = user_home


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
        self._main_config_path = os.path.join(self._config_path, 'karton.cfg')
        self._parser.read([self._main_config_path])

        self._image_paths = None
        self._images = {}

    def _save(self):
        '''
        Save the main configuration to file.
        '''
        with open(self._main_config_path, 'w') as config_file:
            self._parser.write(config_file)

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

    def add_image(self, image_name, content_directory):
        '''
        Add a new image from an existing directory.

        image_name - the name of the image.
        content_directory - the directory where the definition file and other required files are.
        '''
        self._ensure_image_names_loaded()
        assert image_name not in self._image_paths

        image_json_config_path = os.path.join(self._config_path,
                                              'images',
                                              image_name + '.json')

        new_image = ImageConfig(image_name, image_json_config_path, expect_existing=False)
        new_image.content_directory = content_directory
        new_image.save()

        self._image_paths[image_name] = image_json_config_path
        self._images[image_name] = new_image

        return new_image

    def get_aliases(self):
        '''
        Get all the configured aliases.

        return value - a dictionary with the aliases names as keys and instances of ImageAlias as
                       value.
        '''
        aliases = {}

        if not self._parser.has_section('alias'):
            return aliases

        for alias_name, value in self._parser.items('alias'):
            try:
                alias_type, image_name = value.split(';', 1)
            except ValueError:
                verbose('Invalid alias value "%s".' % value)
                continue

            if alias_type == 'run':
                run = True
            elif alias_type == 'control':
                run = False
            else:
                verbose('Invalid alias type "%s".' % alias_type)
                continue

            aliases[alias_name] = ImageAlias(alias_name, image_name, run)

        return aliases

    def add_alias(self, alias):
        '''
        Add a new alias.

        It's the caller's resposibility to make sure that alias.image_name points to an existing
        image.

        alias - the alias to add.
        return value - True if the alias was added, False if it wasn't added because an alias with
                       the same name already exists.
        '''
        existing_aliases = self.get_aliases()
        if alias.alias_name in existing_aliases:
            return False

        if alias.run:
            alias_type = 'run'
        else:
            alias_type = 'control'

        if not self._parser.has_section('alias'):
            self._parser.add_section('alias')

        self._parser.set('alias', alias.alias_name, alias_type + ';' + alias.image_name)
        self._save()

        return True

    def remove_alias(self, alias_name):
        '''
        Remove the alias with name alias_name.

        alias_name - the name of the alias to remove.
        return value - True if the alias was removed, False otherwise.
        '''
        try:
            removed = self._parser.remove_option('alias', alias_name)
        except configparser.NoSectionError:
            removed = False

        if removed:
            self._save()

        return removed
