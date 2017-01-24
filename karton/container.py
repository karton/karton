# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import os
import tempfile

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

        builder = dockerfile.Builder(self._image_config.image_name,
                                     self._image_config.path,
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
