# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import errno
import glob
import json
import os
import re
import sys
import tempfile
import textwrap
import time

from . import (
    alias,
    dockerfile,
    lock,
    pathutils,
    proc,
    version,
    )

from .log import die, info, verbose


class CDError(OSError):
    '''
    An error raised when Karton cannot change the current directory.
    '''

    def __init__(self, directory):
        '''
        Initialize a `CDError`.

        directory:
            The directory (in the image) which cannot be accessed.
        '''
        super(CDError, self).__init__(
            errno.ENOENT,
            textwrap.dedent(
                '''\
                The current directory cannot be accessed in the image:
                    %s

                If you want to make this directory accessible inside the image, you
                can modify the definition.py file and share it using one of the
                sharing methods:
                    - props.share_path(host_path, image_path=None)
                    - props.share_path_in_home(relative_path)
                For more information, see the DefinitionProperties documentation
                at <https://github.com/karton/karton/blob/master/docs/props.md>.

                If you want to execute the command without caring about the current
                directory, see the documentation about --no-cd and --auto-cd by
                typing:

                    karton help run
                ''' % directory).strip())


class Image(object):
    '''
    A Karton image.
    '''

    CD_YES = 100
    CD_NO = 101
    CD_AUTO = 102

    # The basename prefix for the files keeping track of executing commands.
    _RUNNING_COMMAND_PREFIX = 'running-command-'

    def __init__(self, session, image_config):
        '''
        Initialize an `Image` instance.

        All the methods starting with `command_` deal with expected exceptions
        (by calling `log.die` if needed) and are suitable to be called by a command
        line tool. If you want to handle the exceptions by yourself, call the
        method version not prefixed by `command_`.

        session:
            A `runtime.Session`.
        image_config:
            A `configuration.ImageConfig` to configure the image.
        '''
        self._session = session
        self._image_config = image_config

        self._cached_container_content = None

    def command_build(self, no_cache):
        '''
        Build the image.

        no_cache:
            If true, then Docker cached layers are not used to build the image.
            This effectively forces a full rebuild of the image.
        '''
        try:
            self.build(no_cache)
        except dockerfile.DefinitionError as exc:
            die(str(exc))

    def command_start(self):
        '''
        Start the image.
        '''
        self.ensure_container_running()

    def command_stop(self, force):
        '''
        Stop the image.

        force:
            If true, the container is stopped even if commands are running in it.
            If false, the user is asked in case there are programs running.
        '''
        container_id, running_commands = self.status()
        if container_id is None:
            info('Image "%s" is not running.' % self.image_name)
            assert not running_commands
            return

        # This is racy, but it's good enough to avoid having a terminal running something
        # somewhere and accidentally forgetting to close it when stopping the container.
        if running_commands and not force:
            Image._print_running_commands(running_commands)
            info('')
            while True:
                answer = raw_input('Do you really want to stop the image? [Y/N] ')
                answer = answer.lower()
                if answer == 'y':
                    break
                elif answer == 'n':
                    info('')
                    info('Not stopping image %s (Docker container ID: <%s>) with '
                         'running commands.' %
                         (self.image_name, container_id))
                    return

        self.force_stop()

    def command_run(self, cmd_args, cd_mode):
        '''
        Run a command in the image.

        This method doesn't return, but raises `SystemExit` with the exit code of the
        executed command.

        cmd_args:
            The command line (as a list of strings) to execute in the image.
        '''
        self.ensure_container_running()

        try:
            exit_code = self.exec_command(cmd_args, cd_mode)
        except CDError as exc:
            die('%s' % exc.strerror)

        raise SystemExit(exit_code)

    def command_shell(self, cd_mode):
        '''
        Run a shell in the image.

        This method doesn't return, but raises `SystemExit` with the exit code of the
        executed shell.
        '''
        self.ensure_container_running()

        try:
            exit_code = self.exec_command(['bash', '-i'], cd_mode)
        except CDError as exc:
            die('%s' % exc.strerror)

        raise SystemExit(exit_code)

    def command_status(self):
        '''
        Print the status of the image (whether it's running, which commands are running in
        it, etc.).
        '''
        container_id, running_commands = self.status()
        if container_id is None:
            info('Image "%s" is not running.' % self.image_name)
            assert not running_commands
        else:
            info('Image "%s" is running with Docker container ID <%s>.' %
                 (self.image_name, container_id))
            if running_commands:
                Image._print_running_commands(running_commands)
            else:
                info('No commands are running.')

    def command_status_json(self):
        '''
        Print the status of the image (whether it's running, which commands are running in
        it, etc.) as a JSON dictionary.

        This is only for internal use (for instance, for testing).
        '''
        container_id, running_commands = self.status()

        if container_id is None:
            json_dict = {
                'running': False,
                }
        else:
            json_dict = {
                'running': True,
                'container-id': container_id,
                'commands': running_commands
                }

        self._print_json(json_dict)

    def command_image_remove(self, force):
        '''
        Remove the image.

        force:
            If true, the container is stopped even if commands are running in it.
            If false, the user is asked in case there are programs running.
        '''
        self.command_stop(force)

        # If force is True and we still failed (or another one started just now), let's let
        # "docker rmi" take care of it.
        existing_container = self._get_container_id()
        if existing_container and not self.docker.is_container_running(existing_container):
            existing_container = None

        if existing_container is not None and not force:
            die('You need to stop the image before removing it (or use "--force").')

        self._remove_docker_image()

        alias.AliasManager(self._session.config).command_remove_all_for_image(self.image_name)

        content_directory = self._image_config.content_directory

        try:
            self._session.config.remove_image(self.image_name)
        except OSError as exc:
            die('Cannot remove cofiguration file for "%s": %s.' % (self.image_name, exc))

        info('Image "%s" removed. The definition files at "%s" were NOT deleted.' %
             (self.image_name, content_directory))

    def _remove_docker_image(self):
        '''
        Remove the current image.
        '''
        try:
            self.docker.check_output(['rmi', '--force', self.image_name])
        except proc.CalledProcessError:
            verbose('Cannot remove the Docker image for image "%s". '
                    'This probably happened because the Docker image was never built.' %
                    self.image_name)

    @staticmethod
    def command_image_list(config):
        '''
        List existing images.

        config:
            A `configuration.GlobalConfig` instance containing the images.
        '''
        images = config.get_all_images()
        if not images:
            info('No images configured.')
        else:
            for image in images:
                info(' - %s at "%s"' % (image.image_name, image.content_directory))

    @staticmethod
    def command_image_list_json(config):
        '''
        Print a list of existing images as a JSON dictionary

        This is only for internal use (for instance, for testing).

        config:
            A `configuration.GlobalConfig` instance containing the images.
        '''
        json_serializable_images = {}
        for image in config.get_all_images():
            json_serializable_images[image.image_name] = image.json_serializable_config

        Image._print_json(json_serializable_images)

    @staticmethod
    def command_image_create(config, image_name, complete_path):
        '''
        Create a new image.

        config:
            A `configuration.GlobalConfig` instance to which the image should be added.
        image_name:
            The name of the new image (which cannot already exist in config).
        complete_path:
            The path to the directory containing the image definition (and other required
            files).
            The last component of the path must not exist, while the path leading to it
            must already exist.
        '''
        # Python splits the paths differently from other tools. If we make sure that path doesn't
        # contain a trailing slash, then we can split properly between leading path and trailing
        # component.
        verbose('Creating an image called "%s" at "%s".' % (image_name, complete_path))

        complete_path = os.path.abspath(complete_path)
        while complete_path.endswith(os.sep):
            complete_path = complete_path[:-1]

        existing_path = os.path.dirname(complete_path)
        if not os.path.isdir(existing_path):
            die('The path for creating an image should be in the form '
                '"EXISTING-PATH/NEW-IMAGE-DIRECTORY". "%s" is not an existing directory.' %
                existing_path)

        if os.path.exists(complete_path):
            die('The path for creating an image should be in the form '
                '"EXISTING-PATH/NEW-IMAGE-DIRECTORY", where "NEW-IMAGE-DIRECTORY" must not exist, '
                'but "%s" already exists.' %
                complete_path)

        if config.image_with_name(image_name) is not None:
            die('An image called "%s" already exist.' % image_name)

        try:
            os.mkdir(complete_path)
        except OSError as exc:
            die('Cannot create "%s": %s.' % (complete_path, exc))

        definition_file_path = os.path.join(complete_path, 'definition.py')
        with open(definition_file_path, 'w') as definition_file:
            definition_file.write(dockerfile.get_default_definition_file(image_name))

        config.add_image(image_name, complete_path)

        Image._show_help_after_new_image(image_name, definition_file_path)

    @staticmethod
    def command_image_import(config, image_name, existing_dir_path):
        '''
        Create a new image from an exiting definition file.

        config:
            A `configuration.GlobalConfig` instance to which the image should be added.
        image_name:
            The name of the new image (which cannot already exist in config).
        existing_dir_path:
            The path to the directory containing the image definition (and other
            required files).
        '''
        verbose('Creating an image called "%s" from an existing definition at "%s".' %
                (image_name, existing_dir_path))

        existing_dir_path = os.path.abspath(existing_dir_path)
        if not os.path.isdir(existing_dir_path):
            die('The path "%s" should be an existing directory containing the definition file and '
                'other required files. If you want to create a new image without having an '
                'existing definition, use "image create".' % existing_dir_path)

        definition_file_path = os.path.join(existing_dir_path, 'definition.py')
        if not os.path.exists(definition_file_path):
            die('"%s" does not exist. The path should be a directory containing an existing '
                'definition file. If you want to create a new image wihout having an existing '
                'definition, use "image create".' % definition_file_path)

        if config.image_with_name(image_name) is not None:
            die('An image called "%s" already exist.' % image_name)

        config.add_image(image_name, existing_dir_path)

        Image._show_help_after_new_image(image_name, definition_file_path)

    @property
    def _image_data_dir(self):
        '''
        Get the temporary directory where to put image-specific data.

        The directory is created if it doesn't already exist, so you can assume it exists.
        '''
        image_data_dir = os.path.join(self._session.data_dir, self.image_name)
        pathutils.makedirs(image_data_dir)
        return image_data_dir

    @property
    def _running_container_info_path(self):
        '''
        Get the path of the file used to store the currently running container ID.
        '''
        return os.path.join(self._image_data_dir, 'running-container-id')

    @property
    def docker(self):
        '''
        The `dockerctl.Docker` instance.
        '''
        return self._session.docker

    @property
    def image_name(self):
        '''
        The name of the image.
        '''
        return self._image_config.image_name

    def _start_container_lock(self):
        '''
        A `lock.FileLock` for the image used when starting the container.
        '''
        lock_file_path = os.path.join(self._image_data_dir, 'start.lock')

        def timeout_cb():
            die('Cannot acquire the lock for image "%s" at "%s".' %
                (self.image_name, lock_file_path))

        def still_waiting_cb():
            info('Waiting for the Docker container for image "%s" to start.' % self.image_name)

        return lock.FileLock(lock_file_path,
                             timeout_cb=timeout_cb,
                             still_waiting_cb=still_waiting_cb)

    def _load_container_content(self):
        if self._cached_container_content is not None:
            return True

        verbose('Loading existing Docker container info from file "%s".' %
                self._running_container_info_path)
        try:
            with open(self._running_container_info_path, 'r') as container_file:
                content_text = container_file.read()
        except IOError:
            verbose('No stored Docker container ID at "%s".' %
                    self._running_container_info_path)
            return False

        try:
            content = json.loads(content_text)
        except ValueError:
            verbose('The stored content is not JSON, but just the ID')
            content = {
                'id': content_text.strip(),
                }

        if 'id' not in content:
            verbose('Container info is missing some required fields: %s' % content)
            return False

        verbose('Loaded stored container info, the ID is <%s>.' % content['id'])
        self._cached_container_content = content
        return True

    def _get_container_info(self, key, default=None):
        if not self._load_container_content():
            verbose('No cached container content; using default value for key "%s": %s' %
                    (key, default))
            return default

        value = self._cached_container_content.get(key)
        if value is not None:
            verbose('Cached container content and key exist; value for key "%s": %s' %
                    (key, value))
            return value
        else:
            verbose('Cached container content exists, but there is no key "%s"; using default: %s' %
                    (key, default))
            return default

    def _get_container_id(self):
        return self._get_container_info('id')

    def _host_to_container_dir(self, host_dir):
        '''
        Given a directory path on the host, return the corresponding path in the image.

        host_dir:
            A directory path on the host.
        Return value:
            The corresponding path in the image or `None` if not available.
        '''
        def normalize_dir(dir_name):
            if dir_name.endswith('/'):
                return dir_name
            else:
                return dir_name + '/'

        host_dir = normalize_dir(host_dir)

        for mounted_host_dir, mounted_container_dir, _ in reversed(self._image_config.shared_paths):
            mounted_host_dir = normalize_dir(mounted_host_dir)
            mounted_container_dir = normalize_dir(mounted_container_dir)

            if host_dir.startswith(mounted_host_dir):
                return host_dir.replace(mounted_host_dir, mounted_container_dir)

        return None

    def _die_if_old_build_version(self):
        '''
        Check that image was built with the current version of Karton.

        This should only be called when you know there's a built image or the
        result is undefined.
        '''
        if version.numeric_version != self._image_config.built_with_version:
            built_with_str = '.'.join(str(v) for v in self._image_config.built_with_version)
            die('Image "%(image_name)s" was built with Karton %(built_with)s, but the current '
                'version is %(current)s.\n'
                '\n'
                'You need to rebuild the image with:\n'
                '\n'
                '    karton build %(image_name)s' %
                dict(
                    image_name=self.image_name,
                    built_with=built_with_str,
                    current=version.__version__,
                    ))

    def _check_build_time(self):
        '''
        Check if the currently running image was started before the last rebuild of the
        image and, if that is true, print a warning.

        It's an error to call this method if the image is not running.
        '''
        start_time = self._get_container_info('start-time', 0.0)
        if start_time < self._image_config.build_time:
            info('WARNING: Image "%(image_name)s" was re-built after the currently running '
                 'image was started.\n'
                 '\n'
                 'Your command will still be run, but, if you want to make sure that your '
                 'latest changes to the image are picked up, then you should stop the '
                 'currently running one with:\n'
                 '\n'
                 '    karton stop %(image_name)s'
                 '\n' %
                 dict(
                     image_name=self.image_name,
                     ))

    def _run_main_container(self):
        '''
        Actually start the Docker container for the image.
        '''
        verbose('Starting a new container.')

        try:
            images = self.docker.check_output(['images', '-q', self.image_name])
        except proc.CalledProcessError as exc:
            die('Cannot list the available Docker images:\n\n%s' % exc.output)

        images = images.strip()
        if not images:
            die('Image "%(image_name)s" is not available.\n\n'
                'Did you forget to build it? You can build the image with:\n'
                '\n'
                '    karton build %(image_name)s' %
                dict(image_name=self.image_name))

        self._die_if_old_build_version()

        args = [
            'run',
            '--detach',
            '-it',
            '--privileged',
            '--hostname', self._image_config.hostname,
            '--env', 'KARTON_IMAGE=' + self.image_name,
            ]

        default_consistency = self._image_config.default_consistency
        if default_consistency is None:
            # For compatibility with old versions.
            default_consistency = 'consistent'

        supports_consistency = (sys.platform == 'darwin')

        for host_path, container_path, consistency in self._image_config.shared_paths:
            if not os.path.exists(host_path):
                # If the shared path doesn't exist, then Docker creates it. On Linux this means
                # that the new path is owned by root isntead of being owned by the current user.
                pathutils.makedirs(host_path)
            if consistency is None:
                consistency = default_consistency
            path_option = '%s:%s' % (host_path, container_path)
            if supports_consistency:
                path_option += ':' + consistency
            args += ['-v', path_option]

        args += [
            self.image_name,
            '/karton/session_runner.py',
            ]

        try:
            new_container_id = self.docker.check_output(args)
        except proc.CalledProcessError:
            die('Failed to start image "%s".' % self.image_name)

        new_container_id = new_container_id.strip()
        verbose('Started image "%s" with Docker container ID <%s>.' %
                (self.image_name, new_container_id))

        return {
            'id': new_container_id,
            'start-time': time.time(),
            }

    def build(self, no_cache):
        dest_path_base = os.path.join(self._session.data_dir, 'builder')
        pathutils.makedirs(dest_path_base)
        dest_path = tempfile.mkdtemp(prefix=self._image_config.image_name + '-',
                                     dir=dest_path_base)

        builder = dockerfile.Builder(self._image_config,
                                     dest_path,
                                     self._session.host_system)

        try:
            builder.generate()

            args = ['build']
            if no_cache:
                args.append('--no-cache')
            args.extend(['--tag', self._image_config.image_name, dest_path])

            try:
                self._session.docker.check_call(args)
            except proc.CalledProcessError as exc:
                die('Failed to run "karton build" command:\n%s' % exc)

            self._image_config.built_with_version = version.numeric_version
            self._image_config.build_time = time.time()
            self._image_config.save()

        finally:
            builder.cleanup()

    def ensure_container_running(self):
        '''
        Make sure the Docker container is running (i.e. start it if not running already).
        '''
        verbose('Ensuring the Docker container is running.')

        with self._start_container_lock():
            container_id = self._get_container_id()
            if container_id is not None:
                if not self.docker.is_container_running(container_id):
                    container_id = None
                    self._cached_container_content = None

            if container_id is None:
                verbose('No existing Docker container running, starting a new one.')
                new_container_data = self._run_main_container()
                assert new_container_data
                verbose('The new Docker container has ID <%s>.' % new_container_data['id'])
                with open(self._running_container_info_path, 'w') as container_file:
                    # The next call to _get_container_id() won't fail.
                    json.dump(new_container_data,
                              container_file,
                              indent=4,
                              separators=(',', ': '))
                self.exec_commands_for_time('start')
            else:
                verbose('Docker container with ID <%s> already running.' % container_id)

    def force_stop(self):
        '''
        Stop the image (if running), even if commands are currently running in it.

        It's an error to call this method if the image is not running.
        '''
        container_id = self._get_container_id()
        assert container_id

        self.exec_commands_for_time('stop')

        verbose('Stopping Docker container with ID <%s>.' % container_id)

        try:
            self.docker.check_output(['stop', container_id])
        except proc.CalledProcessError:
            verbose('Docker stop command failed.')

        if self.docker.is_container_running(container_id):
            die('Docker container with ID <%s> still running.' % container_id)

        try:
            os.unlink(self._running_container_info_path)
        except OSError as exc:
            verbose('Cannot delete running Docker container ID file at "%s": %s.' %
                    (self._running_container_info_path, exc))

    @staticmethod
    def _get_env_and_cmd_args(cmd_args):
        env_re = re.compile('([a-z_][a-z0-9_]*)=(.*)', re.IGNORECASE)
        env_args = []
        new_cmd_args_index = 0
        for new_cmd_args_index, arg in enumerate(cmd_args):
            match = env_re.match(arg)
            if match is not None:
                env_name = match.group(1)
                env_value = match.group(2)
                env_args.extend([
                    '--env',
                    '%s=%s' % (env_name, env_value),
                    ])

                if new_cmd_args_index == len(cmd_args) - 1:
                    die('foo')

                continue

            if arg == '--':
                # Skip this and stop processing.
                new_cmd_args_index += 1

            break

        return env_args, cmd_args[new_cmd_args_index:]

    def _serialize_execution_data(self, cmd_args):
        for arg in cmd_args:
            # I don't think it should happen, but...
            assert '\0' not in arg

        serialized_data = '\0'.join(cmd_args)
        serialized_data_basename = self._RUNNING_COMMAND_PREFIX + str(os.getpid())
        serialized_data_filename = os.path.join(self._image_data_dir, serialized_data_basename)
        verbose('Registering execution in "%s".' % serialized_data_filename)

        return serialized_data_filename, serialized_data

    def _exec_with_prepared_args(self, orig_cmd_args, actual_docker_args):
        serialized_data_filename, serialized_data = self._serialize_execution_data(orig_cmd_args)
        with open(serialized_data_filename, 'w') as serialized_data_file:
            serialized_data_file.write(serialized_data)

        try:
            exit_code = self.docker.call(actual_docker_args)
        finally:
            verbose('Command finished, removing "%s".' % serialized_data_filename)
            os.remove(serialized_data_filename)

        return exit_code

    def exec_command_only(self, cmd_args, cd_mode=CD_AUTO):
        '''
        Run a command in the (already running) image.

        If the user configured any extra commands to run before or after commands (see
        `DefinitionProperties.run_command`), those are *not* run.
        To run those as well see `exec_command`.

        cmd_args:
            The command line to execute in the image.
        Return value:
            The command's exit code.
        '''
        assert cd_mode in (Image.CD_YES, Image.CD_NO, Image.CD_AUTO)

        container_id = self._get_container_id()
        assert container_id

        self._die_if_old_build_version()
        self._check_build_time()

        if cd_mode == Image.CD_NO:
            verbose('Using the home directory as working directory (as requested).')
            container_dir = None
        else:
            host_cwd = os.getcwd()
            container_dir = self._host_to_container_dir(host_cwd)
            if container_dir is None:
                if cd_mode == Image.CD_AUTO:
                    verbose('Using the home directory as working directory as "%s" is not '
                            'accessible.' % host_cwd)
                else:
                    raise CDError(host_cwd)
            else:
                verbose('Using "%s" as working directory in the image.' % container_dir)

        if container_dir is None:
            container_dir = self._image_config.user_home

        full_args = ['exec']

        # On macOS, HyperKit has some clock syncing problems.
        # Docker has workarounds for a few problems, like the clock being out of sync after a
        # resume, but that doesn't solve the problem completely, so we ask the command runner
        # to fix the clock using hwclock.
        do_sync_opt = 'sync' if self._image_config.auto_clock_sync else 'nosync'

        env_args, cmd_args = self._get_env_and_cmd_args(cmd_args)
        full_args.extend(env_args)

        if sys.stdin.isatty():
            full_args.append('--tty')

        full_args.extend([
            '--interactive',
            container_id,
            '/karton/command_runner.py',
            container_dir,
            do_sync_opt,
            ])
        full_args.extend(cmd_args)

        return self._exec_with_prepared_args(cmd_args, full_args)

    def exec_command(self, cmd_args, cd_mode=CD_AUTO):
        '''
        Run a command in the (already running) image.

        If the user configured any extra commands to run before or after commands (see
        `DefinitionProperties.run_command`), those are run as well.
        To avoid running those as well, see `exec_command_only`.

        cmd_args:
            The command line to execute in the image.
        Return value:
            The command's exit code.
        '''
        self.exec_commands_for_time('before')
        result = self.exec_command_only(cmd_args, cd_mode)
        self.exec_commands_for_time('after')

        return result

    def exec_commands_for_time(self, when):
        '''
        Execute a command specified in the definition file for the specified time.

        See `DefinitionProperties.run_command` for details.

        when:
            The time during the lifetime of the image we are currently at.
        cmd_args:
            The command line to execute in the image.
        '''
        for cmd in self._image_config.run_commands[when]:
            self.exec_command_only(cmd, Image.CD_NO)

    @staticmethod
    def _check_pid_running(pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True

    @staticmethod
    def _print_running_commands(running_commands):
        '''
        Print a list of running commands.

        running_commands:
            A dictionary of commands running inside the image, see `_get_running_commands`
            for the content of the dictionary.
        '''
        info('These commands are still running:')
        for pid, args in running_commands.iteritems():
            # Just for printing, it doesn't need to be perfect.
            args = [a.replace(' ', r'\ ') for a in args]
            info(' - %d: %s' % (pid, ' '.join(args)))

    @staticmethod
    def _print_json(json_object):
        '''
        Pretty prints `json_object` as JSON.

        json_object:
            An object to print out
        '''
        json_string = json.dumps(json_object,
                                 indent=4,
                                 separators=(',', ': '))
        info(json_string)

    def _get_running_commands(self):
        '''
        The commands running in the image.

        Return value:
            A dictionary of PIDs to commands names (the PIDs are for the Karton command
            running on the host, not of the program running inside the image).
        '''
        running_commands_glob = os.path.join(self._image_data_dir,
                                             self._RUNNING_COMMAND_PREFIX + '*')
        commands = {}

        for path in glob.glob(running_commands_glob):
            basename = os.path.basename(path)
            assert basename.startswith(self._RUNNING_COMMAND_PREFIX)

            pid_string = basename[len(self._RUNNING_COMMAND_PREFIX):]
            try:
                pid = int(pid_string)
            except ValueError:
                verbose('Invalid running command file with non-numeric PID "%s" at "%s"; '
                        'ignoring it.' %
                        (pid_string, path))
                continue

            try:
                with open(path, 'r') as cmd_file:
                    args = cmd_file.read().split('\0')
            except IOError:
                # In case the file gets deleted.
                continue

            if not Image._check_pid_running(pid):
                verbose('Program "%s" with PID %d is not running, but it\'s still marked as '
                        'running. It probably crashed.' % (args[0], pid))
                try:
                    os.remove(path)
                except OSError:
                    verbose('Cannot remove running command file "%s" for non-running command.')
                continue

            assert pid not in commands
            commands[pid] = args

        return commands

    def status(self):
        '''
        Status of the image.

        Return value:
            A tuple with two items.
            The first item is the ID of the running Docker container or `None` if the container
            is not running.
            The second is a dictionary of PIDs to commands names (the PIDs are for the Karton
            command running on the host, not for the program running inside the image).
        '''
        container_id = self._get_container_id()
        if container_id is None:
            return None, []

        running = self.docker.is_container_running(container_id)
        if not running:
            verbose('Docker container ID <%s> stored, but it\'s not running.' % container_id)
            return None, []

        return container_id, self._get_running_commands()

    @staticmethod
    def _show_help_after_new_image(image_name, definition_file_path):
        info(textwrap.dedent(
            '''\
            Image "%(image_name)s" added!

            You can now modify the definition file at:
                %(definition_file_path)s

            When you are done, build the image:

                karton build %(image_name)s

            After the image is built, you will only have to build it again if you
            change the definition file.

            You can then run commands in the image like this:

                karton run %(image_name)s COMMAND_NAME ARGUMENT1 ARGUMENT2 ...
            ''' %
            dict(
                image_name=image_name,
                definition_file_path=definition_file_path,
                )
            ).strip())
