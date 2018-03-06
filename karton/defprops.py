# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import collections
import os

from . import (
    compat,
    runtime,
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

    CONSISTENCY_CONSISTENT = 'consistent'
    CONSISTENCY_CACHED = 'cached'
    CONSISTENCY_DELEGATED = 'delegated'

    RUN_AT_BUILD_START = 'at-build-start'
    RUN_AT_BUILD_BEFORE_USER_PKGS = 'at-build-before-user-pkgs'
    RUN_AT_BUILD_END = 'at-build-end'
    RUN_AT_START = 'at-start'
    RUN_BEFORE_COMMAND = 'before-command'
    RUN_AFTER_COMMAND = 'after-command'
    RUN_AT_STOP = 'at-stop'

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
        self._copied = []
        self._image_home_path_on_host = os.path.join(
            runtime.Session.configuration_dir(), 'home-dirs', self._image_name)
        self._username = host_system.username
        self._uid = host_system.uid
        self._user_home = host_system.user_home
        self._hostname = None
        self._distro = 'ubuntu:latest'
        self._architecture = 'x86_64'
        self._packages = []
        self._additional_archs = []
        self._sudo = DefinitionProperties.SUDO_PASSWORDLESS
        self._default_consistency = DefinitionProperties.CONSISTENCY_CONSISTENT
        self._run_commands = collections.defaultdict(list)

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

        return os.path.normpath(os.path.join(self.definition_file_dir, path))

    def _check_not_home_dir(self, host_path):
        '''
        Throw a DefinitionError if `host_path` is the host home directory.
        '''
        host_path = os.path.normpath(host_path)
        host_home = os.path.normpath(self._host_system.user_home)

        if host_path == host_home:
            raise DefinitionError(
                self._definition_file_path,
                'The home directory can only be shared by using:\n'
                '\n'
                '    props.share_whole_home = True'
                )

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
            The third is the consistency.
        '''
        resources = [(self.image_home_path_on_host, self.user_home)]

        for rel_path, consistency in self._shared_home_paths:
            host_path = os.path.join(self._host_system.user_home, rel_path)
            self._check_not_home_dir(host_path)
            image_path = os.path.join(self.user_home, rel_path)
            resources.append((host_path, image_path, consistency))

        for host_path, image_path, consistency in self._shared_paths:
            self._check_not_home_dir(host_path)
            resources.append((host_path, image_path, consistency))

        return resources

    def share_path_in_home(self, relative_path, consistency=None):
        '''
        Share the directory or file at `relative_path` between host and image.

        The path should be relative to the home directory and will be shared in
        the image at the same relative path.
        By default the paths will be identical because the home directory in the
        image and host match, but this can be changed by setting `user_home`.

        relative_path:
            The path, relative to the home directory, to share between host and
            image.
        consistency:
            The consistency level to use to share this path. See `default_consistency`
            for details.
            Use `None` if you want to use the default consistency as set by the
            `default_consistency` property.
            This is ignored on Linux.
        '''
        self._check_consistency_valid(consistency, allow_none=True)
        self._shared_home_paths.append((relative_path, consistency))

    def share_path(self, host_path, image_path=None, consistency=None):
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
        consistency:
            The consistency level to use to share this path. See `default_consistency`
            for details.
            Use `None` if you want to use the default consistency as set by the
            `default_consistency` property.
            This is ignored on Linux.
        '''
        host_path = self.abspath(host_path)

        if image_path is None:
            image_path = host_path

        self._check_consistency_valid(consistency, allow_none=True)
        self._shared_paths.append((host_path, image_path, consistency))

    def copy(self, src_path, dest_path):
        '''
        Copy a file or directory from the host into the image.

        All the files will be owned by root.

        src_path:
            The path to copy into the image.
            It can be an absolute path or a path relative to the current definition file.
        dest_path:
            The absolute path in the image where to copy the file or directory.
        '''
        src_path = self.abspath(src_path)

        if not dest_path.startswith('/'):
            raise DefinitionError(
                self._definition_file_path,
                'The destination path must be absolute.')

        self._copied.append((src_path, dest_path))

    @props_property
    def copied(self):
        '''
        A list of tuples representing the files or directories copied into the image.

        The first element of the tuple is the absolute path in the host of the file or
        directory; the second is the absolute path in the image.
        '''
        return list(self._copied)

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
    def definition_file_dir(self):
        '''
        The path of the directory containing the current definition file.
        '''
        return os.path.dirname(self._definition_file_path)

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
    def uid(self):
        '''
        The uid of the normal non-root user.

        This defaults to the same uid used on the host.
        '''
        return self._uid

    @uid.setter
    def uid(self, uid):
        self._uid = uid

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
        self._check_not_home_dir(path)
        self._image_home_path_on_host = path

    @props_property
    def share_whole_home(self):
        '''
        Whether the whole host home directory is shared as home directory in the image.

        Note that this means that configuration files (like all of your dot-files) modified in
        the image will be modified in the host as well.
        '''
        return self._image_home_path_on_host == self._host_system.user_home

    @share_whole_home.setter
    def share_whole_home(self, share):
        if share == self.share_whole_home:
            return

        if not share:
            raise DefinitionError(
                self._definition_file_path,
                'Cannot reset shared_whole_home after setting it. '
                'Just set a different image_home_path_on_host.')

        self._image_home_path_on_host = self._host_system.user_home

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

    def _check_consistency_valid(self, consistency, allow_none):
        valid_values = [
            'consistent',
            'cached',
            'delegated',
            ]
        if allow_none:
            valid_values.append(None)
        if consistency not in  valid_values:
            raise DefinitionError(self._definition_file_path,
                                  'Invalid consistency value: "%s"' % consistency)

    @props_property
    def default_consistency(self):
        '''
        Content shared between images and host need to be kept consistent.
        If you modify a file on the host it must be updated also in the image
        and vice versa.

        On MacOS, if you don't need perfect instant consistency between the
        two, you can selected a different level of consistency allowing some
        delay in updating either the host or image.
        This slight delay allows for increased performances.

        On Linux, this option is ignored.

        You can select a per-path level of consistency with the `consistency`
        argument to `share_path` and `share_path_in_home`.

        If you have multiple paths to share, you can specify a default consistency
        to use with the `default_consistency` property.

        Valid values are:

        - `DefinitionProperties.CONSISTENCY_CONSISTENT` (the default):
           perfect consistency, i.e. host and image alway have an identical view
           of the file system content.
        - `DefinitionProperties.CONSISTENCY_CACHED`:
           The host's view is authoritative, i.e. updates from the host can be
           delayed before appearing in the image.
        - `DefinitionProperties.CONSISTENCY_DELEGATED`:
           The image's view is authoritative, i.e. updates from the image can be
           delayed before appearing in the host.

        See the [Docker documentation](https://docs.docker.com/docker-for-mac/osxfs-caching/)
        for more details.
        '''
        return self._default_consistency

    @default_consistency.setter
    def default_consistency(self, consistency):
        self._check_consistency_valid(consistency, allow_none=False)
        self._default_consistency = consistency

    def run_command(self, when, *args):
        '''
        Run a shell command at the specified point.

        Commands can be run at different stages of the build phase, when running a command, etc:

        - `DefinitionProperties.RUN_AT_BUILD_START`:
          during the build phase, before any setup or packages are installed.
        - `DefinitionProperties.RUN_AT_BUILD_BEFORE_USER_PKGS`:
          during the build phase, after the base system is setup (including Python), but extra
          packages are not installed yet.
        - `DefinitionProperties.RUN_AT_BUILD_END`:
          during the build phase, at the very end of the Dockerfile.
        - `DefinitionProperties.RUN_AT_START`:
          when the image is started, i.e. when `karton start IMAGE_NAME` is used or when it's
          automatically started because of `karton run IMAGE_NAME COMMAND ARGS`.
        - `DefinitionProperties.RUN_BEFORE_COMMAND`:
          before executing a command, i.e. just before launching `COMMAND ARGS` when doing
          `karton run IMAGE_NAME COMMAND ARGS`.
        - `DefinitionProperties.RUN_AFTER_COMMAND`:
          after executing a command, i.e. just after launching `COMMAND ARGS` when doing
          `karton run IMAGE_NAME COMMAND ARGS`.
          Note that this command is executed even if the invoked command failed.
        - `DefinitionProperties.RUN_AT_STOP`:
          before stopping an image, i.e. when doing `karton stop IMAGE_NAME`.

        Note that, if commands run during the build phase fail (return non-zero), then the build
        will abort.
        On the other hand, the return code of commands run later is ignored.

        when:
            When to run the command.
        *args:
            The command to run and its arguments.
        '''
        self._run_commands[when].append(args)

    def commands_to_run(self, when):
        '''
        Return a list of commands to run at a specific time.

        when:
            The time when to run the commands, see `run_command` for details.
        '''
        return self._run_commands[when]
