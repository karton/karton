# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import json
import threading

try:
    import urllib.request as urllib
except ImportError:
    import urllib2 as urllib


class Updater(object):
    '''
    Check for available updates.
    '''

    def __init__(self, release_url, current_version_string):
        '''
        Initialize an `Updater` instance.

        The check is done in a separate (daemon) thread.
        Whether the check was completed and there's a new version available can be found out
        from the `results` property.

        release_url:
            The URL where a JSON representation of GitHub releases can be found.
            The content of the URL is expected to be a list of releases. Each release should
            have a `tag_name` attribute which contains the current version prefixed by
            a `v` character.
        current_version_string:
            The string representing the currently installed version.
        '''
        self._release_url = release_url
        self._current_version = self._split_version(current_version_string)

        self._updatable_version = None
        self._did_check = False
        self._lock = threading.RLock()

        runner_thread = threading.Thread(target=self._run)
        runner_thread.daemon = True
        runner_thread.start()

    def _run(self):
        try:
            latest = json.load(urllib.urlopen(self._release_url))[0]
            tag_name = latest['tag_name']
            assert tag_name.startswith('v')
            version = self._split_version(tag_name[1:])

            if version > self._current_version:
                with self._lock:
                    self._updatable_version = version
                    self._did_check = True
            else:
                with self._lock:
                    self._did_check = True

        except Exception:
            # This is a daemon thread, so it could be killed at any random point
            # during shutdown. Trying to print anything here could cause problems
            # and cause some error messages from the interpreter being printed on
            # stderr.
            pass

    @staticmethod
    def _split_version(version_string):
        return [int(component) for component in version_string.split('.')]

    @property
    def results(self):
        '''
        A tuple of two elements. The first is True if the check was run, False otherwise.
        The second is the newer version available (as a string), or `None` if no update is
        available.
        '''
        with self._lock:
            if self._updatable_version is None:
                version = None
            else:
                version = '.'.join([str(component) for component in self._updatable_version])

            return self._did_check, version
