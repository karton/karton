# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

try:
    # Python 2.
    from ConfigParser import (
        SafeConfigParser,
        NoSectionError,
        NoOptionError,
        )
    ConfigParser = SafeConfigParser
except ImportError:
    # Python 3.
    from configparser import (
        ConfigParser,
        NoSectionError,
        NoOptionError,
        )

import collections
import errno
import glob
import json
import os
import sys

from . import (
    compat,
    pathutils,
    )

from .log import die, info, verbose


ImageAlias = collections.namedtuple('ImageAlias', ['alias_name', 'image_name', 'implied_command'])


class ImageConfig(object):
    '''
    Configuration for a single image definition.
    '''

    def __init__(self, image_name, json_config_path, expect_existing=True):
        '''
        Initialize an `ImageConfig` instance.

        image_name:
            The user-visible image name.
        json_config_path:
            The path to the JSON configuration file for the image.
        expect_existing:
            If True, an exception will be raised if the file does not exist already.
            If False, the non-existance of the file will be ignore, useful when
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

        if self._json_config_path is None:
            info('Configuration for image "%s" cannot be saved as the image was removed.' %
                 self._image_name)
            return

        pathutils.makedirs(os.path.dirname(self._json_config_path))

        with open(self._json_config_path, 'w') as json_file:
            json.dump(self.json_serializable_config,
                      json_file,
                      indent=4,
                      separators=(',', ': '))

    @property
    def json_serializable_config(self):
        '''
        A dictionary suitable for JSON represantation for this object.
        '''
        return self._content

    def remove(self):
        '''
        Remove the configuration file for the image.

        After a call to this method, this instance should not be used any more.

        If the file cannot be removed, the original `OSError` exception is raised.
        '''
        try:
            os.unlink(self._json_config_path)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                # This can happen if we create an ImageConfig and try to remove it before
                # saving it, so there's nothing to worry about.
                # Even if this is not the case... meh, after all we just wanted to remove
                # the file.
                verbose('Configuration file "%s" for image "%s" doesn\'t exist, so there is '
                        'no need to remove it.'
                        % (self._image_name, self._json_config_path))
            else:
                raise

        self._json_config_path = None

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
        A sequence of three-items tuples representing the directories or files shared between
        host and image.

        The first tuple element is the path on the host, the second one is the path in the
        image, the third is the consistency level.
        '''
        result = []

        for shared_details in self._content.get('shared-paths', ()):
            if len(shared_details) == 2:
                # Old versions didn't have the consistency value.
                shared_details = (shared_details[0], shared_details[1], None)
            result.append(shared_details)

        return tuple(result)

    @shared_paths.setter
    def shared_paths(self, paths):
        self._content['shared-paths'] = paths

    @property
    def default_consistency(self):
        '''
        The default consistency to use for all the paths without a specified consistency.

        See `DefinitionProperties.default_consistency` for details.
        '''
        return self._content.get('default-consistency', None)

    @default_consistency.setter
    def default_consistency(self, default_consistency):
        self._content['default-consistency'] = default_consistency

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

    @property
    def _platform_needs_clock_sync(self):
        return sys.platform == 'darwin'

    @property
    def auto_clock_sync(self):
        '''
        Whether to automatically synchronise the image clock with the host one.

        This is needed only on macOS, so the value is always False on Linux.
        '''
        return self._content.get('auto-clock-sync', self._platform_needs_clock_sync)

    @auto_clock_sync.setter
    def auto_clock_sync(self, auto_sync):
        if not self._platform_needs_clock_sync:
            return

        self._content['auto-clock-sync'] = auto_sync

    @property
    def built_with_version(self):
        '''
        A tuple of integers representing the Karton version used to build the
        image.
        '''
        return tuple(self._content.get('built-with-version', (0, 0, 0)))

    @built_with_version.setter
    def built_with_version(self, version):
        self._content['built-with-version'] = version

    @property
    def build_time(self):
        '''
        A floating number representing the time (in seconds since the epoch) when
        this image was built last.
        '''
        return self._content.get('build-time', 0.0)

    @build_time.setter
    def build_time(self, build_time):
        self._content['build-time'] = build_time

    @property
    def run_commands(self):
        '''
        A dictionary of commands to run at different points in the lifetime of a running image.

        The valid keys are `'start'`, `'before'`, `'after'`, `'stop'`.

        Values are lists of strings (the first element of a list is the program to execute, the
        others are the arguments to that program).
        '''
        return collections.defaultdict(list, self._content.get('run-commands', {}))

    @run_commands.setter
    def run_commands(self, commands):
        self._content['run-commands'] = commands


class GlobalConfig(object):
    '''
    Read and write the Karton configuration files.
    '''

    def __init__(self, config_path):
        '''
        Initialize a `GlobalConfig` object.

        filename:
            The path for the configuration file (which doesn't need to exist).
        '''
        self._config_path = config_path

        self._parser = ConfigParser()
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
        Make sure that the configuration for the images has been loaded into
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

    def get_all_images(self):
        '''
        Get all the configured images.

        Return value:
            A list of `ImageConfig` instances.
        '''
        self._ensure_image_names_loaded()

        images = []
        for image_name in self._image_paths:
            images.append(self.image_with_name(image_name))

        return images

    def image_with_name(self, image_name):
        '''
        Return the `ImageConfig` instance representing the configuration for
        the image called `image_name` or `None` if the image doesn't exist.

        image_name:
            The name of the image
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

        image_name:
            The name of the image.
        content_directory:
            The directory where the definition file and other required files are.
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

    def remove_image(self, image_name):
        '''
        Remove an existing image.

        If the image cannot be removed, the original `OSError` from the failing `os.unlink`
        is propagated.

        image_name:
            The name of the image to remove (which must exist).
        '''
        image_config = self.image_with_name(image_name)
        assert image_config

        image_config.remove() # Don't catch exceptions on purpose.

        del self._image_paths[image_name]
        del self._images[image_name]

    def _get(self, section, option, default=None):
        '''
        Get the value of a global option.

        This works around `ConfigParser`'s oddities with sections.

        section:
            The section where the option is.
        option:
            The name of the option.
        default:
            A value to return if the option doesn't exist.
        Return value:
            The value of the option (or default if the option doesn't exist).
        '''
        try:
            return self._parser.get(section, option)
        except (NoSectionError, NoOptionError):
            return default

    def _get_items(self, section):
        '''
        Get all the global options in a section.

        This works around `ConfigParser`'s oddities with sections.

        section:
            The section where the options are.
        Return value:
            An ordered dictionary (`collection.OrderedDict`) of options and their values.
        '''
        try:
            items = self._parser.items(section)
        except NoSectionError:
            items = []

        return collections.OrderedDict(items)

    def _set(self, section, option, value):
        '''
        Set the value of a global option.

        This works around `ConfigParser`'s oddities with sections.

        section:
            The section where the option is.
        option:
            The name of the option.
        value:
            The new value of the option.
        '''
        if not self._parser.has_section(section):
            self._parser.add_section(section)

        self._parser.set(section, option, value)
        self._save()

    def _remove(self, section, option):
        '''
        Remove a global option.

        This works around `ConfigParser`'s oddities with sections.

        section:
            The section where the option is.
        option:
            The name of the option.
        Return value:
            `True` if the option was removed, `False` otherwise.
        '''
        try:
            removed = self._parser.remove_option(section, option)
        except NoSectionError:
            removed = False

        if removed:
            self._save()

        return removed

    def get_aliases(self):
        '''
        Get all the configured aliases.

        Return value:
            A dictionary with the alias names as keys and instances of `ImageAlias` as value.
        '''
        aliases = {}

        for alias_name, value in compat.iteritems(self._get_items('alias')):
            try:
                implied_command, image_name = value.split(';', 1)
            except ValueError:
                verbose('Invalid alias value "%s".' % value)
                continue

            if implied_command == 'NONE':
                implied_command = None

            aliases[alias_name] = ImageAlias(alias_name, image_name, implied_command)

        return aliases

    def get_alias(self, alias_name):
        '''
        Get the alias named `alias_name`.

        alias_name:
            The name of the alias for retrieve.
        Return value:
            The `Alias` instance corresponding to `alias_name` or `None` if the alias is
            not configured.
        '''
        return self.get_aliases().get(alias_name)

    def add_alias(self, alias):
        '''
        Add a new alias.

        It's the caller's resposibility to make sure that `alias.image_name` points to an
        existing image.

        alias:
            The alias to add.
        Return value:
            `True` if the alias was added, `False` if it wasn't added because an alias
            with the same name already exists.
        '''
        existing_aliases = self.get_aliases()
        if alias.alias_name in existing_aliases:
            return False

        implied_command = alias.implied_command
        if implied_command is None:
            implied_command = 'NONE'

        self._set('alias', alias.alias_name, implied_command + ';' + alias.image_name)

        return True

    def remove_alias(self, alias_name):
        '''
        Remove the alias with name `alias_name`.

        alias_name:
            The name of the alias to remove.
        Return value:
            `True` if the alias was removed, `False` otherwise.
        '''
        return self._remove('alias', alias_name)

    @property
    def alias_symlink_directory(self):
        '''
        The directory where to put symlinks used for aliases.
        '''
        return self._get('general', 'alias-symlink-directory')

    @alias_symlink_directory.setter
    def alias_symlink_directory(self, directory):
        self._set('general', 'alias-symlink-directory', directory)

    @property
    def last_update_check(self):
        '''
        The last time (in seconds since the epoch) when we checked for an update.
        '''
        last_check_time_string = self._get('general', 'last-update-check', 0)
        try:
            return int(last_check_time_string)
        except ValueError:
            verbose('Invalid configuration for last-update-check, integer expected but got "%s".' %
                    last_check_time_string)
            return 0

    @last_update_check.setter
    def last_update_check(self, last_check_time):
        self._set('general', 'last-update-check', str(last_check_time))
