# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import json
import os
import time

from karton import (
    updater,
    )

from mixin_tempdir import TempDirMixin
from tracked import TrackedTestCase


class UpdateTestCase(TrackedTestCase,
                     TempDirMixin):
    '''
    Test `updater.Updater`.
    '''

    @staticmethod
    def wait_for_results(url, curr_version, timeout_secs=30):
        '''
        Get the results from an `updater.Updater` retrying automatically until they are
        available (or a timeout).
        update_check = updater.Updater('file://' + local_release_path, '1.2.3')

        url:
            The URL (potentially a `file://` one) where the get the releases from (in the JSON
            format used by GitHub).
        curr_version:
            The currently installed version of the software.
        timeout_secs:
            The approximate number of seconds to wait before giving up.
        '''

        check_interval = 0.1
        update_check = updater.Updater(url, curr_version)

        for _ in range(int(float(timeout_secs) / check_interval)):
            did_check, new_version = update_check.results
            if did_check:
                break
            time.sleep(check_interval)

        return did_check, new_version

    def test_updater(self):
        local_release_path = os.path.join(self.tmp_dir, 'releases')
        local_release_url = 'file://' + local_release_path
        with open(local_release_path, 'w') as local_release_file:
            json.dump(
                [
                    {
                        'tag_name': 'v1.2.4',
                        'random_stuff': 'Hello',
                    },
                    {
                        'tag_name': 'v1.2.3',
                    },
                    {
                        'tag_name': 'v1.2',
                        'something': 42,
                    },
                ],
                local_release_file)

        did_check, new_version = self.wait_for_results(local_release_url, '1.2.3')
        self.assertTrue(did_check)
        self.assertEqual(new_version, '1.2.4')

        did_check, new_version = self.wait_for_results(local_release_url, '1.2.4')
        self.assertTrue(did_check)
        self.assertIsNone(new_version)

        did_check, new_version = self.wait_for_results(local_release_url, '1.2.5')
        self.assertTrue(did_check)
        self.assertIsNone(new_version)
