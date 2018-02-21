# Copyright (C) 2017-2018 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import imp
import os
import shutil
import traceback

from . import (
    compat,
    emit,
    )

from .defprops import (
    DefinitionError,
    DefinitionProperties,
    )


_DEFAULT_DEFINITION_FILE = '''\
# This file defines how to build the image for "%(image_name)s".
#
# This is a standard Python file where you can use all the features you would
# use in a normal Python script.
# The file needs to contain a setup_image function which accepts a single
# argument of type DefinitionProperties.

def setup_image(props):
    \'\'\'
    Called when "%(image_name)s" needs to be built.

    The props argument allow you to set various properties for the image to
    be built.
    See <https://github.com/karton/karton/blob/master/docs/props.md> for the
    full documentation of the props object.
    \'\'\'

    # The Linux distribution to use.
    # This string is formed by two parts separated by a ":".
    # The first part is the name of the distro ("ubuntu", "debian", "fedora", or
    # "centos").
    # The second part is the version to use and is optional. If omitted the latest
    # version of the distribution is used.
    # Examples of valid values are: "ubuntu:latest", "fedora:25", "debian",
    # "ubuntu:devel", etc.
    # This name matches the name used by Docker.
    #props.distro = 'ubuntu:latest'

    # You will probably want to make some directory from the host accessible in the
    # image as well.
    # For instance you can share your ~/src directory like this:
    #props.share_path_in_home('src')
    # props.share_path_in_home will just share a path inside your home directory inside
    # the image's home directory. The path under the home will be the same in host and
    # image.

    # If you want to share a path outside your home you can use props.share_path:
    #props.share_path('/foo')

    # The path in the image and host system can be different:
    #props.share_path('/path/on/host', '/different/path/in/image')

    # Sharing is not limited to directories, but single files can be shared as well.

    # Probably you will want to install some extra packages inside the image.
    # props.packages is a list of packages to be installed and you can add more if you
    # want.
    #props.packages.extend(['gcc', 'some-other-package-name'])
'''


def get_default_definition_file(image_name):
    return _DEFAULT_DEFINITION_FILE % dict(
        image_name=image_name,
        )


class Builder(object):
    '''
    Build a `Dockerfile` file and related files.
    '''

    def __init__(self, image_config, dst_dir, host_system):
        '''
        Initialize a `Builder` instance.

        image_config:
            The `configuration.ImageConfig` instance for the image to build.
        dst_dir:
            The directory where to put the `Dockerfile` file and related files.
        '''
        self._image_config = image_config
        self._dst_dir = dst_dir
        self._host_system = host_system

    @staticmethod
    def _prepare_image_setup(definition_directory):
        '''
        Get the setup function for the definition file in `definition_directory`.

        definition_directory:
            The directory where `definition.py` is.
        Return value:
            The `setup_image` function for the specified image definition and the path
            of the definition file.
        '''
        # Load the definition file.
        definition_path = os.path.join(definition_directory, 'definition.py')

        try:
            with open(definition_path) as definition_file:

                try:
                    definition = imp.load_module(
                        'definition',
                        definition_file,
                        definition_path,
                        ('.py', 'r', imp.PY_SOURCE))
                except Exception as exc:
                    raise DefinitionError(
                        definition_path,
                        'The definition file "%s" couldn\'t be loaded because it contains an '
                        'error: %s.\n\n%s' % (definition_path, exc, traceback.format_exc()))

        except IOError as exc:
            raise DefinitionError(
                definition_path,
                'The definition file "%s" couldn\'t be opened: %s.\n\n%s' %
                (definition_path, exc, traceback.format_exc()))

        # Get the setup_image function.
        setup_image = getattr(definition, 'setup_image', None)
        if setup_image is None:
            raise DefinitionError(
                definition_path,
                'The definition file "%s" doesn\'t contain a "setup_image" method (which should '
                'accept an argument of type "DefinitionProperties")' % definition_path)

        try:
            args_spec = compat.getargspec(setup_image)
        except TypeError as exc:
            raise DefinitionError(
                definition_path,
                'The definition file "%s" does contain a "setup_image" attribute, but it should be '
                'a method accepting an argument of type "DefinitionProperties"' % definition_path)

        if len(args_spec.args) != 1:
            raise DefinitionError(
                definition_path,
                'The definition file "%s" does contain a "setup_image" method, but it should '
                'accept a single argument of type "DefinitionProperties"' % definition_path)

        return setup_image, definition_path

    def generate(self):
        '''
        Prepare the directory with the `Dockerfile` and all the other required
        files.

        If something goes wrong due to the user configuration or definition
        file, then a `DefinitionError` is raised.
        '''
        # Load the user's definition.
        setup_image, definition_path = \
            self._prepare_image_setup(self._image_config.content_directory)

        # Execute it.
        props = DefinitionProperties(self._image_config.image_name,
                                     definition_path,
                                     self._host_system,
                                     self._prepare_image_setup)

        try:
            setup_image(props)
        except BaseException as exc:
            raise DefinitionError(
                definition_path,
                'An exception was raised while executing "setup_image" from the definition '
                'file "%s": %s.\n\n%s' %
                (definition_path, exc, traceback.format_exc()))

        # And finally generate the docker-related files from the DefinitionProperties.
        self._generate_docker_stuff(props)

    def _generate_docker_stuff(self, props):
        '''
        Generate the `Dockerfile` file and all the other related files.

        props:
            The `DefinitionProperties` instance contianing information on what to
            put in the `Dockerfile` file and which other files are needed.
        '''

        emitter = emit.Emitter(props, self._dst_dir)
        content = emitter.generate_content()

        with open(os.path.join(self._dst_dir, 'Dockerfile'), 'w') as output:
            output.write(content)

        self._image_config.shared_paths = props.get_path_mappings()
        self._image_config.default_consistency = props.default_consistency
        self._image_config.hostname = props.hostname
        self._image_config.user_home = props.user_home
        # We can set the clock only if we have passwordless sudo.
        self._image_config.auto_clock_sync = props.sudo == DefinitionProperties.SUDO_PASSWORDLESS
        self._image_config.run_commands = {
            'start':  props.commands_to_run(props.RUN_AT_START),
            'before': props.commands_to_run(props.RUN_BEFORE_COMMAND),
            'after':  props.commands_to_run(props.RUN_AFTER_COMMAND),
            'stop':   props.commands_to_run(props.RUN_AT_STOP),
            }
        self._image_config.save()

    def cleanup(self):
        '''
        Remove intermediate files created to build the image.
        '''
        shutil.rmtree(self._dst_dir)
