# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import imp
import os
import shutil
import textwrap
import traceback

from . import (
    compat,
    locations,
    pathutils,
    runtime,
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


class DefinitionError(Exception):
    '''
    An error due to the user image definition containing mistakes.
    '''

    def __init__(self, definition_file_path, msg):
        '''
        Initialize a `DefinitionError` instance.

        definition_file_path:
            The path of the definition file which caused the error.
        msg:
            The exception error message.
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
    _g_props_all_properties[compat.get_func_name(fget)] = fget
    return property(fget, *args, **kwargs)


class DefinitionProperties(object):
    '''
    The `DefinitionProperties` class defines how to generate an image: which packages
    to install, which base distro to use, which files and directories to share, etc.
    '''

    SUDO_WITH_PASSWORD = 101
    SUDO_PASSWORDLESS = 102
    SUDO_NO = 103

    _ARCHITECTURES = {
        'x86_64': '',
        'aarch64': 'aarch64/',
        'armv7': 'armhf/',
        }

    def __init__(self, image_name, definition_file_path, host_system, prepare_definition_import):
        '''
        Initializes a `DefinitionProperties` instance.
        '''
        self._image_name = image_name
        self._definition_file_path = definition_file_path
        self._host_system = host_system
        self._prepare_definition_import = prepare_definition_import

        self._shared_home_paths = []
        self._shared_paths = []
        self._image_home_path_on_host = os.path.join(
            runtime.Session.configuration_dir(), 'home-dirs', self._image_name)
        self._username = host_system.username
        self._user_home = host_system.user_home
        self._hostname = None
        self._distro = 'ubuntu:latest'
        self._architecture = 'x86_64'
        self._packages = []
        self._additional_archs = []
        self._sudo = DefinitionProperties.SUDO_PASSWORDLESS

        self.maintainer = None

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

    def abspath(self, path):
        '''
        Make `path` absolute.

        If `path` is relative, it is considered relative to the definition file which is
        currently being parsed.
        If it's already absolute, then nothing is done.

        path:
            The path to make absolute if it's relative.
        Return value:
            An absolute path.
        '''
        if path.startswith('/'):
            return path

        return os.path.normpath(
            os.path.join(os.path.dirname(self._definition_file_path),
                         path))

    def get_path_mappings(self):
        '''
        The list of resources shared between host and guest.

        You should call this only after setting things like the home directory location which
        could change some of these values.

        Return value:
            A list of tuples.
            The first element of the tuple is the location of the shared directory or file on
            the host.
            The second is the location inside the image.
        '''
        resources = [(self.image_home_path_on_host, self.user_home)]

        for rel_path in self._shared_home_paths:
            host_path = os.path.join(self._host_system.user_home, rel_path)
            image_path = os.path.join(self.user_home, rel_path)
            resources.append((host_path, image_path))

        for host_path, image_path in self._shared_paths:
            resources.append((host_path, image_path))

        return resources

    def share_path_in_home(self, relative_path):
        '''
        Share the directory or file at `relative_path` between host and image.

        The path should be relative to the home directory and will be shared in
        the image at the same relative path.
        By default the paths will be identical because the home directory in the
        image and host match, but this can be changed by setting `user_home`.

        relative_path:
            The path, relative to the home directory, to share between host and
            image.
        '''
        self._shared_home_paths.append(relative_path)

    def share_path(self, host_path, image_path=None):
        '''
        Share the directory or file at `host_path` with the image where it will be
        accessible as `image_path`.

        If `image_path` is `None` (the default), then it will be accessible at the
        same location in both host and container.

        host_path:
            The path on the host system of the directory or file to share.
            If it's a relative path, then it's relative to the currently parsed
            definition file.
        image_path:
            The path in the container where the file or directory will be accessible,
            or None to use the same path in both host and container.
            Defaults to `None`.
        '''
        host_path = self.abspath(host_path)

        if image_path is None:
            image_path = host_path

        self._shared_paths.append((host_path, image_path))

    def import_definition(self, other_definition_directory):
        '''
        Import an existing definition file.

        other_definition_directory:
            The path of the directory where the definition file is.
            It can be an absolute path or a path relative to the current definition file.
        '''
        other_definition_directory = self.abspath(other_definition_directory)

        setup_image, other_definition_path = \
            self._prepare_definition_import(other_definition_directory)

        outer_definition_path = self._definition_file_path
        self._definition_file_path = other_definition_path

        setup_image(self)

        self._definition_file_path = outer_definition_path

    @props_property
    def definition_file_path(self):
        '''
        The path to the current definition file.
        '''
        return self._definition_file_path

    @props_property
    def image_name(self):
        '''
        The mame of the image.
        '''
        return self._image_name

    @props_property
    def username(self):
        '''
        The name of the normal non-root user.

        This defaults to the same user name used on the host.
        '''
        return self._username

    @username.setter
    def username(self, username):
        # FIXME: check for the validity of the new username
        self._username = username

    @props_property
    def user_home(self):
        '''
        The path (valid inside the image) of the non-root user home directory.

        It's recommended to keep the home directory identical in the host and image.
        This helps in case any tool writes an image path into a file which is later
        accessed on the host.
        '''
        return self._user_home

    @user_home.setter
    def user_home(self, user_home):
        self._user_home = user_home

    @props_property
    def image_home_path_on_host(self):
        '''
        The path on the host where to store the content of the non-root user home directory.

        By default, the home directory of the non-root user gets saved on the host. This
        allows configuration files to persist across invocations.

        You should not set this to the host home directory to avoid messing up your
        configuration files, for instance if you have different versions of the same
        program running on the host and inside the image.

        By default, this is set to `~/.karton/home-dirs/IMAGE-NAME`.
        '''
        return self._image_home_path_on_host

    @image_home_path_on_host.setter
    def image_home_path_on_host(self, path):
        self._image_home_path_on_host = path

    @props_property
    def packages(self):
        '''
        A list of packages to install in the image.

        The package names are those used by the distro you are using for the image.

        Note that some packages, like `python`, will be installed automatically by
        Karton as they are needed for it to work. You should not rely on this and
        explicitly install everything you need.
        '''
        return self._packages

    @props_property
    def hostname(self):
        '''
        The hostname for the image.

        The default value is `IMAGE_NAME-on-HOST-HOSTNAME`.
        '''
        if self._hostname is not None:
            return self._hostname
        else:
            return '%s-on-%s' % (self._image_name, self._host_system.hostname)

    @hostname.setter
    def hostname(self, hostname):
        self._hostname = hostname

    @props_property
    def distro(self):
        '''
        The distro used for the image.

        This is in the Docker format, i.e. the distro name, a colon and the tag name.
        If you don't specify the tag when setting the distro, "latest" is used.

        The default distro is `ubuntu:latest`, that is the most recent LTS version
        of Ubuntu.
        '''
        return self._distro

    @distro.setter
    def distro(self, distro):
        split = distro.split(':')
        if len(split) == 1:
            distro_name = split[0]
            distro_tag = 'latest'
        elif len(split) == 2:
            distro_name, distro_tag = split
        else:
            raise DefinitionError(self._definition_file_path,
                                  'Invalid distro: "%s"' % distro)

        if distro_name not in ('ubuntu', 'debian', 'centos', 'fedora'):
            raise DefinitionError(self._definition_file_path,
                                  'Invalid distro name: "%s"' % distro_name)

        self._distro = distro_name + ':' + distro_tag

    @props_property
    def distro_components(self):
        '''
        The distro used for the image as a tuple.
        The first item is the distro name, the second the tag.
        '''
        split = self._distro.split(':')
        assert len(split) == 2
        return tuple(split)

    @props_property
    def distro_name(self):
        '''
        The name of the distro without any tag.
        '''
        # pylint: disable=unsubscriptable-object
        return self.distro_components[0]

    @props_property
    def distro_tag(self):
        '''
        The tag part of the distro name.
        '''
        # pylint: disable=unsubscriptable-object
        return self.distro_components[1]

    @props_property
    def deb_based(self):
        '''
        Whether the currently selected distro is based on Debian (i.e. it's Debian or Ubuntu).
        '''
        return self.distro_name in ('debian', 'ubuntu')

    @props_property
    def rpm_based(self):
        '''
        Whether the currently selected distro is based on RPM packages (i.e. it's CentOS or
        Fedora).
        '''
        return self.distro_name in ('centos', 'fedora')

    @props_property
    def docker_distro_full_name(self):
        '''
        The name of the distro as it will be used in the Dockerfile.

        This may be different from `distro` if an architecture was specified.
        '''
        return self._ARCHITECTURES[self._architecture] + self.distro

    @props_property
    def architecture(self):
        '''
        The architecture for the image.

        Possible values are:

        - `x86_64` (default value if you don't specify anything): Also known as x64, x86-64,
          or amd64. This is the normal 64-bit architecture for most computers.
        - `armv7`: 32-bit ARMv7.
        - `aarch64`: 64-bit ARMv8.

        Note that not every distro is supported on every architecture.
        In particular, the Docker support for ARM is experimental and may break at any
        point (and it actually does, quite often).
        '''
        return self._architecture

    @architecture.setter
    def architecture(self, architecture):
        if architecture not in self._ARCHITECTURES:
            raise DefinitionError(
                self._definition_file_path,
                'Invalid architecture "%s", only these architectures are supported: %s.' %
                (architecture, self._ARCHITECTURES.keys()))

        self._architecture = architecture

    @props_property
    def additional_archs(self):
        '''
        A list of additional architectures to support in the image.

        This is, for instance, useful to install 32-bit packages on a 64-bit distro.

        The only value currently supported is `'i386'` and is supported only on Debian
        and Ubuntu.
        '''
        return self._additional_archs

    @props_property
    def sudo(self):
        '''
        Whether to install the `sudo` command and whether passwordless `sudo` should
        be allowed.

        Possible values are:

        - `DefinitionProperties.SUDO_PASSWORDLESS` (the default):
          install `sudo` and don't require a password.
        - `DefinitionProperties.SUDO_WITH_PASSWORD`:
          install `sudo` but require a password.
        - `DefinitionProperties.SUDO_NO`:
          don't install `sudo`.
        '''
        return self._sudo

    @sudo.setter
    def sudo(self, sudo):
        if sudo not in (DefinitionProperties.SUDO_PASSWORDLESS,
                        DefinitionProperties.SUDO_WITH_PASSWORD,
                        DefinitionProperties.SUDO_NO):
            raise DefinitionError(self._definition_file_path,
                                  'Invalid sudo policy value: "%s"' % sudo)

        self._sudo = sudo


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
                        yum makecache fast && \
                        yum install -y \
                            %(what)s
                    ''' %
                    dict(what=what_string))
            else:
                assert False, 'Not Debian nor RPM-based but supported?'

        emit('# Generated by Karton.')
        emit()

        emit('FROM %s' % props.docker_distro_full_name)
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

        if props.deb_based:
            emit_install('apt-utils')
            emit_install('locales')

        if props.sudo != DefinitionProperties.SUDO_NO:
            emit_install('sudo')

        emit_install('python')

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
                useradd -m -s /bin/bash --home-dir %(user_home)s %(username)s && \
                chown %(username)s %(user_home)s
            ENV USER %(username)s
            USER %(username)s
            '''
            % dict(
                username=props.username,
                user_home=props.user_home,
                ))

        # After this point everything will be run as the normal user, not root!

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
        Remove intermediate files created to build the image.
        '''
        shutil.rmtree(self._dst_dir)
