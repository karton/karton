# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import imp
import inspect
import os
import re
import shutil
import textwrap
import traceback

from log import verbose


class DefinitionError(Exception):
    '''
    An error due to the user image definition containing mistakes.
    '''

    def __init__(self, definition_file_path, msg):
        '''
        Initializes a DefinitionError instance.

        definition_file_path - The path of the definition file which caused the error.
        msg - The exception error message.
        '''
        super(DefinitionError, self).__init__(msg)

        self._definition_file_path = definition_file_path

    @property
    def definition_file_path(self):
        '''
        The path of the definition file which caused the error to happen.
        '''
        return self._definition_file_path


class DefinitionProperties(object):
    '''
    Instructions on how to generate the image and what to include in it.
    '''

    _eval_regex = re.compile(r'\$\(([a-zA-Z0-9._-]*)\)')

    def __init__(self, image_name, definition_file_path, host_system):
        '''
        Initializes a DefinitionProperties instance.
        '''
        self._image_name = image_name
        self._definition_file_path = definition_file_path
        self._host_system = host_system

        self._distro = 'ubuntu'
        self._packages = []

        self.maintainer = None

        self._eval_map = {
            'host.username': lambda: self._host_system.username,
            'host.userhome': lambda: self._host_system.user_home,
            'host.hostname': lambda: self._host_system.hostname,
            }

    def eval(self, in_string):
        '''
        Replaces variables in in_string and returns the new string.

        FIXME: Document the variable syntanx and valid variables.
        '''
        def eval_cb(match):
            var_name = match.group(1)
            replacement_cb = self._eval_map.get(var_name)
            if replacement_cb is None:
                raise DefinitionError(
                    self._definition_file_path,
                    'The variable "$(%s)" is not valid (in string "%s").' %
                    (var_name, match.string))
            return replacement_cb()

        return self._eval_regex.sub(eval_cb, in_string)

    @property
    def image_name(self):
        return self._image_name

    @property
    def packages(self):
        return self._packages

    @property
    def distro(self):
        return self._distro

    @distro.setter
    def set_distro(self, distro):
        # FIXME: handle tags.
        if distro not in ('ubuntu', 'debian'):
            raise DefinitionError(self._definition_file_path,
                                  'Invalid distibution: "%s".' % distro)

        self._distro = distro


class Builder(object):
    '''
    Builds a Dockerfile and related files.
    '''

    def __init__(self, image_name, src_dir, dst_dir, host_system):
        '''
        Initializes a Builds instance.

        image_name - the name of the image.
        src_dir - the directory where the definition file and other files are.
        dst_dir - the directory where to put the Dockerfile and related files.
        '''
        self._image_name = image_name
        self._src_dir = src_dir
        self._dst_dir = dst_dir
        self._host_system = host_system

    def generate(self):
        '''
        Prepare the directory with the Dockerfile and all the other required
        files.

        If something goes wrong due to the user configuration or definition
        file, then a DefinitionError is raised.
        '''

        # Load the definition file.
        definition_path = os.path.join(self._src_dir, 'definition.py')

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
                'accept an argument of type "DefinitionProperties").' % definition_path)

        try:
            args_spec = inspect.getargspec(setup_image)
        except TypeError as exc:
            raise DefinitionError(
                definition_path,
                'The definition file "%s" does contain a "setup_image" attribute, but it should be '
                'a method accepting an argument of type "DefinitionProperties".' % definition_path)

        if len(args_spec.args) != 1:
            raise DefinitionError(
                definition_path,
                'The definition file "%s" does contain a "setup_image" method, but it should '
                'accept a single argument of type "DefinitionProperties".' % definition_path)

        # Execute it.
        props = DefinitionProperties(self._image_name, definition_path, self._host_system)

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
        Generate the Dockerfile file and all the other related files.

        props - The DefinitionProperties instance contianing information on what to
                put in the Dockerfile and which other files are needed.
        '''
        lines = []

        def emit(text=''):
            if not text.endswith('\n'):
                text += '\n'
            if text.startswith('\n') and len(text) > 1:
                text = text[1:]
            lines.append(textwrap.dedent(text))

        emit('# Generated by Karton.')
        emit()

        emit('FROM %s' % props.distro)
        emit()

        if props.maintainer:
            emit('MAINTAINER %s' % props.maintainer)
            emit()

        emit(
            r'''
            RUN \
                export DEBIAN_FRONTEND=noninteractive && \
                apt-get update -qqy && \
                apt-get install -qqy -o=Dpkg::Use-Pty=0 \
                    --no-install-recommends \
                    apt-utils \
                    && \
                apt-get install -qqy -o=Dpkg::Use-Pty=0 \
                    locales
            ''')

        if props.packages:
            packages = ' '.join(props.packages)
            emit(
                r'''
                RUN \
                    export DEBIAN_FRONTEND=noninteractive && \
                    sed -e 's|^# en_GB.UTF-8|en_GB.UTF-8|g' -i /etc/locale.gen && \
                    locale-gen && \
                    TERM=xterm apt-get install -qqy -o=Dpkg::Use-Pty=0 \
                        %s
                ''' % packages)

        emit(
            r'''
            RUN \
                apt-get clean -qq
            ''')

        content = ''.join(lines).strip() + '\n'
        verbose('The Dockerfile is:\n========%s========' % content)

        with open(os.path.join(self._dst_dir, 'Dockerfile'), 'w') as output:
            output.write(content)

    def cleanup(self):
        '''
        Removes intermediate files created to build the image.
        '''
        shutil.rmtree(self._dst_dir)
