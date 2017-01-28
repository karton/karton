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

import dirs
import pathutils

from log import verbose


_DEFAULT_DEFINITION_FILE = '''\
# This file defines how to build the image for "%(image_name)s".
#
# This is a standard Python file where you can use all the featurs you would use in a normal
# Python script.
# The file needs to contain a setup_image function which accepts a single argument.

def setup_image(props):
    \'\'\'
    Called when "%(image_name)s" needs to be built.

    The props argument allow you to set various properties for the image to be built.
    \'\'\'

    # By default the username for the image is the same as the one on the host machine,
    # this can be overwritten by setting the username property.
    #props.username = 'john'

    # Similarly the home directory is at the same location in both host and image, but
    # it can be overwritten. The directory will be create automatically.
    #props.user_home = '/home/john.smith'

    # The props.eval method allow you to replace variables inside a string.
    # The variables are in the form "$(VARIABLE_NAME)".
    # For instance you could set the hostname of the image to be the name of the host
    # hostname, followed by a dash and then followed by the image name:
    #props.hostname = props.eval('$(host.hostname)-$(image.name)')

    # You will probably want to make some directory from the host accessible in the
    # container as well.
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

    # The home directory from the container should be saved on the host or all the
    # configuration files and other changes you make to your user will be lost.
    # It's better not to share your host home directory in the image as that could lead
    # to confusion and messing up of your configuration files (which could be accessed
    # by two different version of the same program on host and container).
    # The props.container_home_path_on_host property allow you to set where to save
    # the image home directory. If unset, it will be in a sub-directory of "~/.karton".
    #props.container_home_path_on_host = props.eval('$(host.userhome)/MyImageHomeDir')


    # You are likely to want to install some extra packages inside the container.
    # props.packages is a list of packages to be installed and you can add more if you
    # want.
    #props.packages.extend(['vim', 'some-package-I-need'])
'''


def get_default_definition_file(image_name):
    return _DEFAULT_DEFINITION_FILE % dict(
        image_name=image_name,
        )


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


_g_props_all_properties = {}

def props_property(fget, *args, **kwargs):
    _g_props_all_properties[fget.func_name] = fget
    return property(fget, *args, **kwargs)


class DefinitionProperties(object):
    '''
    Instructions on how to generate the image and what to include in it.
    '''

    _eval_regex = re.compile(r'\$\(([a-zA-Z0-9._-]*)\)')

    SUDO_WITH_PASSWORD = 101
    SUDO_PASSWORDLESS = 102
    SUDO_NO = 103

    def __init__(self, image_name, definition_file_path, host_system):
        '''
        Initializes a DefinitionProperties instance.
        '''
        self._image_name = image_name
        self._definition_file_path = definition_file_path
        self._host_system = host_system

        self._shared_home_paths = []
        self._shared_paths = []
        self._container_home_path_on_host = os.path.join(host_system.user_home,
                                                         '.karton',
                                                         'home-dirs',
                                                         self._image_name)
        self._username = host_system.username
        self._user_home = host_system.user_home
        self._hostname = None
        self._distro = 'ubuntu'
        self._packages = []
        self._additional_archs = []
        self._sudo = DefinitionProperties.SUDO_PASSWORDLESS

        self.maintainer = None

        self._eval_map = {
            'host.username': lambda: self._host_system.username,
            'host.userhome': lambda: self._host_system.user_home,
            'host.hostname': lambda: self._host_system.hostname,
            'image.name': lambda: self._image_name,
            }

    def __str__(self):
        res = [
            'DefinitionProperties(image_name=%s, definition_file_path=%s, host_system=%s)' %
            (
                repr(self._image_name),
                repr(self._definition_file_path),
                repr(self._host_system),
            )
            ]
        for prop_name, getter in _g_props_all_properties.iteritems():
            res.append('    %s = %s' % (prop_name, repr(getter(self))))
        return '\n'.join(res)

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

    def get_path_mappings(self):
        '''
        The list of resources shared between host and guest.

        You should call this only after setting things like the home directory location which
        could change some of these values.

        return value - a list of tuples; the first element of the tuple is the location of the
                       share directory or file on the host, the second is the location in the
                       container.
        '''
        resources = [(self.container_home_path_on_host, self.user_home)]

        for rel_path in self._shared_home_paths:
            host_path = os.path.join(self._host_system.user_home, rel_path)
            container_path = os.path.join(self.user_home, rel_path)
            resources.append((host_path, container_path))

        for host_path, container_path in self._shared_paths:
            resources.append((host_path, container_path))

        return resources

    def share_path_in_home(self, relative_path):
        '''
        Share the directory or file at relative_path between host and image.

        relative_path - the path to share at the same location in both host and container;
                        the path must a subdirectory of the home directory and relative to it.
        '''
        self._shared_home_paths.append(relative_path)

    def share_path(self, host_path, container_path=None):
        '''
        Share the directory or file at host_path with the container where it will be accessible
        as container_path.

        If container_path is None, then it will be accessible at the same location in both host
        and container.

        host_path - the path on the host system of the directory or file to share.
        container_path - the path in the container where the file or directory will be accessible,
                         or None to use the same path in both host and container.
        '''
        if container_path is None:
            container_path = host_path

        self._shared_paths.append((host_path, container_path))

    @props_property
    def image_name(self):
        return self._image_name

    @props_property
    def username(self):
        return self._username

    @username.setter
    def username(self, username):
        # FIXME: check for the validity of the new username
        self._username = username

    @props_property
    def user_home(self):
        return self._user_home

    @user_home.setter
    def user_home(self, user_home):
        '''
        Sets the user home directory for the user in the container.

        It's recommended to keep the home directory identical in the host and
        container. This helps in case any tool write a container path into a
        file that is later accessed from the host.
        '''
        self._user_home = user_home

    @props_property
    def container_home_path_on_host(self):
        '''
        The path on the host where to store the content of the container home
        directory.

        You should not set this to the host home directory to avoid messing up
        your configuration files.
        '''
        return self._container_home_path_on_host

    @container_home_path_on_host.setter
    def container_home_path_on_host(self, path):
        self._container_home_path_on_host = path

    @props_property
    def packages(self):
        return self._packages

    @props_property
    def hostname(self):
        '''
        The hostname for the container.

        The default value is "IMAGE_NAME-on-HOST-HOSTNAME".
        '''
        if self._hostname is not None:
            return self._hostname
        else:
            return self.eval('$(image.name)-on-$(host.hostname)')

    @hostname.setter
    def hostname(self, hostname):
        self._hostname = hostname

    @props_property
    def distro(self):
        return self._distro

    @distro.setter
    def distro(self, distro):
        # FIXME: handle tags.
        if distro not in ('ubuntu', 'debian'):
            raise DefinitionError(self._definition_file_path,
                                  'Invalid distibution: "%s".' % distro)

        self._distro = distro

    @props_property
    def additional_archs(self):
        return self._additional_archs

    @props_property
    def sudo(self):
        return self._sudo

    @sudo.setter
    def sudo(self, sudo):
        if sudo not in (DefinitionProperties.SUDO_PASSWORDLESS,
                        DefinitionProperties.SUDO_WITH_PASSWORD,
                        DefinitionProperties.SUDO_NO):
            raise DefinitionError(self._definition_file_path,
                                  'Invalid sudo policy value: "%s".' % sudo)

        self._sudo = sudo


class Builder(object):
    '''
    Builds a Dockerfile and related files.
    '''

    def __init__(self, image_config, dst_dir, host_system):
        '''
        Initializes a Builds instance.

        image_config - the configuration.ImageConfig instance for the image to build.
        dst_dir - the directory where to put the Dockerfile and related files.
        '''
        self._image_config = image_config
        self._dst_dir = dst_dir
        self._host_system = host_system

        self._copyable_files_dir = os.path.join(self._dst_dir, 'files')
        pathutils.makedirs(self._copyable_files_dir)

    def generate(self):
        '''
        Prepare the directory with the Dockerfile and all the other required
        files.

        If something goes wrong due to the user configuration or definition
        file, then a DefinitionError is raised.
        '''

        # Load the definition file.
        definition_path = os.path.join(self._image_config.content_directory, 'definition.py')

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
        props = DefinitionProperties(self._image_config.image_name,
                                     definition_path,
                                     self._host_system)

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
        Allow the file at path host_file_path (on the host) to be copied to the image by
        creating a hard link to it from the directory sent to the Docker daemon.

        return value - the path of the hard link, relative to the destination directory.
        '''
        # FIXME: what if two files have the same basenames?
        link_path = os.path.join(self._copyable_files_dir, os.path.basename(host_file_path))
        os.link(host_file_path, link_path)

        assert link_path.startswith(self._dst_dir)
        return os.path.relpath(link_path, start=self._dst_dir)

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

        props.packages.append('python')

        if props.sudo != DefinitionProperties.SUDO_NO:
            props.packages.append('sudo')

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

        emit(
            r'''
            RUN \
                mkdir -p $(dirname %(user_home)s) && \
                useradd -m -s /bin/bash --home-dir %(user_home)s %(username)s && \
                chown %(username)s %(user_home)s
            ENV USER %(username)s
            USER %(username)s
            '''
            % dict(
                username=props.username,
                user_home=props.user_home,
                ))

        container_code_path = os.path.join(dirs.root_code_dir(), 'container-code')
        for container_script in ('session_runner.py', 'command_runner.py'):
            path = os.path.join(container_code_path, container_script)
            copyable_path = self._make_file_copyable(path)
            emit('ADD %s /karton/%s' %
                 (copyable_path, container_script))
        emit()

        content = ''.join(lines).strip() + '\n'
        verbose('The Dockerfile is:\n========\n%s========' % content)

        with open(os.path.join(self._dst_dir, 'Dockerfile'), 'w') as output:
            output.write(content)

        self._image_config.shared_paths = props.get_path_mappings()
        self._image_config.hostname = props.hostname
        self._image_config.user_home = props.user_home
        self._image_config.save()

    def cleanup(self):
        '''
        Removes intermediate files created to build the image.
        '''
        shutil.rmtree(self._dst_dir)
