# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import errno
import glob
import json
import os
import tempfile
import time

import alias
import dockerctl
import dockerfile
import lock
import pathutils
import proc

from log import die, info, verbose


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
            'Host directory "%s" cannot be accessed in the image' % directory)


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

        self._cached_container_id = None

    def command_build(self):
        '''
        Build the image.
        '''
        try:
            self.build()
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
            die('%s.' % exc.strerror)

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
            die('%s.' % exc.strerror)

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

    def command_remove(self, force):
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
            self.docker.check_call(['rmi', '--force', self.image_name])
        except proc.CalledProcessError:
            die('Cannot remove the image.')

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

        with open(os.path.join(complete_path, 'definition.py'), 'w') as definition_file:
            definition_file.write(dockerfile.get_default_definition_file(image_name))

        config.add_image(image_name, complete_path)

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
    def _running_container_id_file_path(self):
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

    def _get_container_id(self):
        if self._cached_container_id is not None:
            return self._cached_container_id

        verbose('Loading Docker container ID from file "%s".' %
                self._running_container_id_file_path)
        try:
            with open(self._running_container_id_file_path, 'r') as container_file:
                container_id = container_file.read().strip()
                verbose('The stored Docker container ID is <%s>.' % container_id)
                return container_id
        except IOError:
            verbose('No stored Docker container ID at "%s".' % self._running_container_id_file_path)
            return None

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

        for mounted_host_dir, mounted_container_dir in reversed(self._image_config.shared_paths):
            mounted_host_dir = normalize_dir(mounted_host_dir)
            mounted_container_dir = normalize_dir(mounted_container_dir)

            if host_dir.startswith(mounted_host_dir):
                return host_dir.replace(mounted_host_dir, mounted_container_dir)

        return None

    def _run_main_container(self):
        '''
        Actually start the Docker container for the image.
        '''
        verbose('Starting a new container.')

        try:
            images = self.docker.check_output(['images', '-q', self.image_name],
                                              stderr=proc.STDOUT)
            images = images.strip()
        except proc.CalledProcessError as exc:
            dockerctl.die_docker_not_running(exc.output)

        if not images:
            die('Image "%s" is not available. Try building it with "build" first.' %
                self.image_name)

        args = [
            'run',
            '--detach',
            '-it',
            '--privileged',
            '--hostname', self._image_config.hostname,
            ]

        for host_path, container_path in self._image_config.shared_paths:
            args += ['-v', '%s:%s' % (host_path, container_path)]

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
        return new_container_id

    def build(self):
        dest_path_base = os.path.join(self._session.data_dir, 'builder')
        pathutils.makedirs(dest_path_base)
        dest_path = tempfile.mkdtemp(prefix=self._image_config.image_name + '-',
                                     dir=dest_path_base)

        builder = dockerfile.Builder(self._image_config,
                                     dest_path,
                                     self._session.host_system)

        try:
            builder.generate()

            self._session.docker.call(
                ['build', '--tag', self._image_config.image_name, dest_path])

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

            if container_id is None:
                verbose('No existing Docker container running, starting a new one.')
                new_container_id = self._run_main_container()
                verbose('The new Docker container has ID <%s>.' % new_container_id)
                assert new_container_id
                with open(self._running_container_id_file_path, 'w') as container_file:
                    # The next call to _get_container_id() won't fail.
                    container_file.write(new_container_id)
            else:
                verbose('Docker container with ID <%s> already running.' % container_id)

    def force_stop(self):
        '''
        Stop the image (if running), even if commands are currently running in it.

        It's an error to call this method if the image is not running.
        '''
        container_id = self._get_container_id()
        assert container_id

        verbose('Stopping Docker container with ID <%s>.' % container_id)

        try:
            self.docker.check_output(['stop', container_id])
        except proc.CalledProcessError:
            verbose('Docker stop command failed.')

        if self.docker.is_container_running(container_id):
            die('Docker container with ID <%s> still running.' % container_id)

        try:
            os.unlink(self._running_container_id_file_path)
        except OSError as exc:
            verbose('Cannot delete running Docker container ID file at "%s": %s.' %
                    (self._running_container_id_file_path, exc))

    def exec_command(self, cmd_args, cd_mode=CD_AUTO):
        '''
        Run a command in the (already running) image.

        cmd_args:
            The command line to execute in the image.
        Return value:
            The command's exit code.
        '''
        assert cd_mode in (Image.CD_YES, Image.CD_NO, Image.CD_AUTO)

        container_id = self._get_container_id()
        assert container_id

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

        full_args = [
            'exec',
            '-it',
            '--env', 'KARTON_IMAGE=' + self.image_name,
            container_id,
            '/karton/command_runner.py',
            container_dir,
            str(int(time.time())),
            ]
        full_args.extend(cmd_args)

        for arg in cmd_args:
            # I don't think it should happen, but...
            assert '\0' not in arg

        serialized_data = '\0'.join(cmd_args)
        serialized_data_basename = self._RUNNING_COMMAND_PREFIX + str(os.getpid())
        serialized_data_filename = os.path.join(self._image_data_dir, serialized_data_basename)
        verbose('Registering execution in "%s".' % serialized_data_filename)

        try:
            with open(serialized_data_filename, 'w') as serialized_data_file:
                serialized_data_file.write(serialized_data)

            exit_code = self.docker.call(full_args)

        finally:
            verbose('Command finished, removing "%s".' % serialized_data_filename)
            os.remove(serialized_data_filename)

        return exit_code

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
