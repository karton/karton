# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import imp
import json
import os
import shutil
import textwrap
import traceback

from . import (
    compat,
    locations,
    pathutils,
    )

from .defprops import (
    DefinitionError,
    DefinitionProperties,
    )

from .log import verbose


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

        self._copyable_files_dir = os.path.join(self._dst_dir, 'files')
        pathutils.makedirs(self._copyable_files_dir)

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

    def _make_file_copyable(self, host_file_path):
        '''
        Allow the file at path `host_file_path` (on the host) to be copied to the image by
        creating a hard link to it from the directory sent to the Docker daemon.

        Return value:
            The path of the hard link, relative to the destination directory.
        '''
        # FIXME: what if two files have the same basenames?
        link_path = os.path.join(self._copyable_files_dir, os.path.basename(host_file_path))
        pathutils.hard_link_or_copy(host_file_path, link_path)

        assert link_path.startswith(self._dst_dir)
        return os.path.relpath(link_path, start=self._dst_dir)

    def _generate_docker_stuff(self, props):
        '''
        Generate the `Dockerfile` file and all the other related files.

        props:
            The `DefinitionProperties` instance contianing information on what to
            put in the `Dockerfile` file and which other files are needed.
        '''
        lines = []

        def emit(text=''):
            if not text.endswith('\n'):
                text += '\n'
            if text.startswith('\n') and len(text) > 1:
                text = text[1:]
            lines.append(textwrap.dedent(text))

        def emit_install(*what):
            if not what:
                return

            what_string = ' '.join(what)

            # We need to update the package lists every time due to Docker's caching of
            # intermediate images as a previous layer could have been installed with now
            # stale package list.
            if props.deb_based:
                emit(
                    r'''
                    # Installing %(what)s.
                    RUN \
                        export DEBIAN_FRONTEND=noninteractive && \
                        apt-get update -qqy && \
                        apt-get install -qqy -o=Dpkg::Use-Pty=0 \
                            --no-install-recommends \
                            %(what)s
                    ''' %
                    dict(what=what_string))
            elif props.rpm_based:
                emit(
                    r'''
                    # Installing %(what)s.
                    RUN \
                        yum install -y \
                            %(what)s
                    ''' %
                    dict(what=what_string))
            else:
                assert False, 'Not Debian nor RPM-based but supported?'

        def emit_run(when):
            for args in props.commands_to_run(when):
                emit(
                    r'''
                    RUN \
                        %(json_cmd)s
                    ''' %
                    dict(
                        json_cmd=json.dumps(args),
                        ))

        emit('# Generated by Karton.')
        emit()

        emit('FROM %s' % props.docker_distro_full_name)
        emit()

        if props.maintainer:
            emit('MAINTAINER %s' % props.maintainer)
            emit()

        emit_run(props.RUN_AT_BUILD_START)

        if props.additional_archs:
            archs_run = ['RUN \\']
            for i, arch in enumerate(props.additional_archs):
                if i == len(props.additional_archs) - 1:
                    cont = ''
                else:
                    cont = ' && \\'
                archs_run.append('    dpkg --add-architecture %s%s' % (arch, cont))
            archs_run.append('')
            archs_run.append('')
            emit('\n'.join(archs_run))

        if props.deb_based:
            emit_install('apt-utils')
            emit_install('locales')

        if props.sudo != DefinitionProperties.SUDO_NO:
            emit_install('sudo')

        emit_install('python')

        emit_run(props.RUN_AT_BUILD_BEFORE_USER_PKGS)

        if props.packages:
            emit_install(*props.packages)

        if props.deb_based:
            emit(
                r'''
                RUN apt-get clean -qq
                ''')
        elif props.rpm_based:
            emit(
                r'''
                RUN yum clean all
                ''')

        if props.sudo != DefinitionProperties.SUDO_NO:
            sudoers_path = os.path.join(self._dst_dir, 'sudoers')

            with open(sudoers_path, 'w') as sudoers_file:
                if props.sudo == DefinitionProperties.SUDO_PASSWORDLESS:
                    nopasswd = 'NOPASSWD: '
                else:
                    nopasswd = ''

                sudoers_file.write(textwrap.dedent(
                    '''\
                    root ALL=(ALL) ALL
                    %(username)s ALL=(ALL) %(nopasswd)sALL
                    Defaults    env_reset
                    Defaults    secure_path="%(paths)s"
                    ''' %
                    dict(
                        username=props.username,
                        nopasswd=nopasswd,
                        paths='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                        )
                    ))

            emit(
                r'''
                COPY sudoers /etc/sudoers
                RUN chmod 440 /etc/sudoers
                ''')

        container_code_path = os.path.join(locations.root_code_dir(), 'container-code')
        for container_script in ('session_runner.py', 'command_runner.py'):
            path = os.path.join(container_code_path, container_script)
            copyable_path = self._make_file_copyable(path)
            emit(
                r'''
                ADD %(copyable_path)s /karton/%(container_script)s
                RUN chmod +x /karton/%(container_script)s
                '''
                % dict(
                    copyable_path=copyable_path,
                    container_script=container_script,
                    ))

        emit(
            r'''
            RUN \
                mkdir -p $(dirname %(user_home)s) && \
                useradd -m -s /bin/bash --home-dir %(user_home)s --uid %(uid)s %(username)s && \
                chown %(username)s %(user_home)s
            ENV USER %(username)s
            USER %(username)s
            '''
            % dict(
                username=props.username,
                uid=props.uid,
                user_home=props.user_home,
                ))

        # After this point everything will be run as the normal user, not root!

        emit_run(props.RUN_AT_BUILD_END)

        content = ''.join(lines).strip() + '\n'
        verbose('The Dockerfile is:\n========\n%s========' % content)

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
