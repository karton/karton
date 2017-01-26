# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import glob
import os
import tempfile
import time

import dockerctl
import dockerfile
import lock
import pathutils
import proc

from log import die, info, verbose


class Image(object):
    '''
    A Karton image.
    '''

    # The basename prefix for the files keeping track of executing commands.
    _RUNNING_COMMAND_PREFIX = 'running-command-'

    def __init__(self, session, image_config):
        '''
        Initializes an Image instance.

        All the methods starting with "command_" deal with expected exceptions
        (by calling log.die if needed) and are suitable to be called by a command
        line tool. If you want to handle the exceptions by yourself, call the
        method version not prefixed by "command_".

        session - a runtime.Session.
        image_config - a configuration.ImageConfig to configure the image.
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

    def command_run(self, cmd_args):
        '''
        Run a command in the image.

        This method doesn't return, but raises SystemExit with the exit code of the
        executed command.

        cmd_args - the command line to execute in the image.
        '''
        self.ensure_container_running()
        exit_code = self.exec_command(cmd_args)
        raise SystemExit(exit_code)

    def command_status(self):
        '''
        Print the status of the image (whether it's running, which commands are running in
        it, etc.
        '''
        container_id, running_commands = self.status()
        if container_id is None:
            info('The container for image "%s" is not running.' % self.image_name)
            assert not running_commands
        else:
            info('The container for image "%s" is running with ID <%s>.' %
                 (self.image_name, container_id))
            if running_commands:
                Image._print_running_commands(running_commands)
            else:
                info('No commands are running.')

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
        Get the path of the file used to store the currently running contained ID.
        '''
        return os.path.join(self._image_data_dir, 'running-container-id')

    @property
    def docker(self):
        '''
        The dockerctl.Docker instance.
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
        A lock.FileLock() for the image used when starting the container.
        '''
        lock_file_path = os.path.join(self._image_data_dir, 'start.lock')

        def timeout_cb():
            die('Cannot acquire the container lock for image "%s" at "%s".' %
                (self.image_name, lock_file_path))

        def still_waiting_cb():
            info('Waiting for the container to start.')

        return lock.FileLock(lock_file_path,
                             timeout_cb=timeout_cb,
                             still_waiting_cb=still_waiting_cb)

    def _get_container_id(self):
        if self._cached_container_id is not None:
            return self._cached_container_id

        verbose('Loading container ID from file "%s".' % self._running_container_id_file_path)
        try:
            with open(self._running_container_id_file_path, 'r') as container_file:
                container_id = container_file.read().strip()
                verbose('The stored ID is <%s>.' % container_id)
                return container_id
        except IOError:
            verbose('No stored container ID at "%s".' % self._running_container_id_file_path)
            return None

    def _run_main_container(self):
        verbose('Starting a new container.')

        try:
            images = self.docker.check_output(['images', '-q', self.image_name],
                                              stderr=proc.STDOUT)
            images = images.strip()
        except proc.CalledProcessError as exc:
            dockerctl.die_docker_not_running(exc.output)

        if not images:
            die('The container image "%s" is not available. Try building it with "build" first.' %
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
            die('Failed to start the container.')

        new_container_id = new_container_id.strip()
        verbose('Started container with ID <%s>.' % new_container_id)
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
        Make sure the container is running (i.e. start it if not running already).
        '''
        verbose('Ensuring the container is running.')

        with self._start_container_lock():
            container_id = self._get_container_id()
            if container_id is not None:
                if not self.docker.is_container_running(container_id):
                    container_id = None

            if container_id is None:
                verbose('No container running, starting a new one.')
                new_container_id = self._run_main_container()
                verbose('The new container has ID <%s>.' % new_container_id)
                assert new_container_id
                with open(self._running_container_id_file_path, 'w') as container_file:
                    # The next call to _get_container_id() won't fail.
                    container_file.write(new_container_id)
            else:
                verbose('Container with ID <%s> already running.' % container_id)

    def exec_command(self, cmd_args):
        '''
        Run a command in the (already running) image.

        cmd_args - the command line to execute in the image.
        return value - the command's exit code.
        '''
        container_id = self._get_container_id()
        assert container_id

        container_dir = '/' # FIXME

        full_args = [
            'exec',
            '-it',
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

        running_commands - a dictionary of commands running inside the container, see
                           _get_running_commands for the content of the dictionary.
        '''
        info('These commands are still running:')
        for pid, args in running_commands.iteritems():
            # Just for printing, it doesn't need to be perfect.
            args = [a.replace(' ', r'\ ') for a in args]
            info(' - %d: %s' % (pid, ' '.join(args)))

    def _get_running_commands(self):
        '''
        The commands running in the container.

        return value - a dictionary of PIDs to commands names (the PIDs are of the Karton command
                       running on the host, not of the program running in the container).
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

        return value - a tuple with two items, the first one is the ID of the running container
                       or None if the container is not running, the second is a dictionary of
                       PIDs to commands names (the PIDs are of the Karton command running on the
                       host, not of the program running in the container).
        '''
        container_id = self._get_container_id()
        if container_id is None:
            return None, []

        running = self.docker.is_container_running(container_id)
        if not running:
            verbose('Container <%s> stored, but it\'s not running.' % container_id)
            return None, []

        return container_id, self._get_running_commands()
