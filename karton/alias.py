# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import json
import os
import textwrap

from . import (
    compat,
    configuration,
    locations,
    pathutils,
    )

from .log import die, info, verbose


class AliasManager(object):
    '''
    Deal with adding, removing and listing aliases.

    Aliases are used to access Karton without having to specify an image every time.

    All the methods starting with `command_` deal with expected exceptions
    (by calling `log.die` if needed) and are suitable to be called by a command
    line tool.
    '''

    def __init__(self, config):
        '''
        Initialize a AliasManager instance.

        config:
            A configuration.GlobalConfing instance used to store the aliases and
            corresponding images.
        '''
        self._config = config

    def command_show_all(self):
        '''
        Print information about all the aliases.
        '''
        aliases = self._config.get_aliases()
        for alias_name in sorted(aliases):
            alias = aliases[alias_name]
            self._print_alias(alias)

    def command_show_all_json(self):
        '''
        Print information about all the aliases as a JSON dictionary.

        This is only for internal use (for instance, for testing).
        '''
        aliases = self._config.get_aliases()
        alias_json_dict = {}
        for alias_name in sorted(aliases):
            alias = aliases[alias_name]
            alias_json_dict[alias_name] = {
                'image-name': alias.image_name,
                'implied-command': alias.implied_command,
                }

        json_string = json.dumps(alias_json_dict,
                                 indent=4,
                                 separators=(',', ': '))
        info(json_string)

    def command_show(self, alias_name):
        '''
        Print information about the alias with name `alias_name`.

        alias_name:
            The name of the alias.
        '''
        aliases = self._config.get_aliases()
        try:
            alias = aliases[alias_name]
        except KeyError:
            die('"%s" is not a known alias.' % alias_name)

        self._print_alias(alias)

    def command_add(self, alias_name, image_name, implied_command):
        '''
        Add an alias.

        alias_name:
            The name of the alias to add.
        image_name:
            The name of the image the alias should use.
        implied_command:
            A command to automatically use for this alias or `None` if a
            command needs to be specified on the command line explicitly.
        '''
        verbose('Adding alias "%s" for image "%s" (implied command: %s)' %
                (alias_name, image_name, implied_command))

        # Create the alias in our configuration.
        image = self._config.image_with_name(image_name)
        if image is None:
            die('Cannot add alias "%s" for image "%s" as the image does not exist.' %
                (alias_name, image_name))

        alias = configuration.ImageAlias(alias_name, image_name, implied_command)
        if not self._config.add_alias(alias):
            die('Cannot add alias "%s" for image "%s" as an alias with the same name already '
                'exists.' %
                (alias_name, image_name))

        # Actually create the file.
        created = False
        try:
            for path in pathutils.get_system_executable_paths():
                existing_program = os.path.join(path, alias_name)
                if os.path.isfile(existing_program):
                    die('Cannot create alias "%s" as it would overwrite the "%s" program.' %
                        (alias_name, existing_program))

            alias_symlink_directory = self._ensure_alias_symlink_directory()
            alias_symlink_path = os.path.join(alias_symlink_directory, alias_name)

            executable = locations.get_karton_executable()
            verbose('Creating alias symlink from "%s" to "%s".' % (alias_symlink_path, executable))
            try:
                os.symlink(executable, alias_symlink_path)
            except OSError as exc:
                die('Cannot create symbolic link "%s" (from "%s") for the alias: %s.' %
                    (alias_symlink_path, executable, exc))

            created = True

        finally:
            if not created:
                verbose('Removing alias "%s" as the symlink was not created.' % alias_name)
                self._config.remove_alias(alias_name)

    def command_remove(self, alias_name):
        '''
        Remove an alias with name `alias_name`.

        alias_name:
            The name of the alias to remove.
        '''
        # Do we have the alias?
        if not self._config.get_alias(alias_name):
            die('Alias "%s" as it does not exist.' % alias_name)

        # Is the alias symlink directory configured?
        directory = self._config.alias_symlink_directory
        if directory is None:
            die('Alias "%s" exists, but the directory for the alias is not configured, so it '
                'cannot be removed.')

        # Is the symlink in place?
        symlink = os.path.join(directory, alias_name)

        # If somebody deletes the symlink, we should still work.
        if os.path.exists(symlink):
            if not os.path.islink(symlink):
                die('Alias file "%s" for alias "%s" is not a symbolic link. '
                    'The alias cannot be removed.' %
                    (symlink, alias_name))
            symlink_target = os.path.abspath(os.path.realpath(symlink))
            if symlink_target != locations.get_karton_executable():
                die('Alias symblic link "%s" for alias "%s" is not a valid symbolic link for an '
                    'alias. The target path is not the Karton executable but "%s".' %
                    (symlink, alias_name, symlink_target))

            # And now we can delete the symlink.
            try:
                os.unlink(symlink)
            except OSError as exc:
                die('Cannot delete the symbolic link "%s" for alias "%s", so the alias cannot be '
                    'removed: %s.' %
                    (symlink, alias_name, exc))

        # Finally delete the alias from our configuration.
        # We do this last as it can fail only if there's a programming error.
        removed = self._config.remove_alias(alias_name)
        assert removed

    def command_remove_all_for_image(self, image_name):
        '''
        Remove all the aliases for an image.

        image_name:
            The name of the image for which the aliases should be removed.
        '''
        verbose('Removing all aliases for image "%s".' % image_name)

        for alias in compat.itervalues(self._config.get_aliases()):
            if alias.image_name == image_name:
                verbose('Alias "%s" is for the target image "%s" so it will be removed.' %
                        (alias.alias_name, image_name))
                self.command_remove(alias.alias_name)

    def _ensure_alias_symlink_directory(self):
        directory = self._config.alias_symlink_directory
        if directory is None:
            directory = self._config.alias_symlink_directory = \
                self._choose_alias_symlink_directory()

        return directory

    @staticmethod
    def _choose_alias_symlink_directory():
        info(textwrap.dedent(
            '''\
            Aliases are created by creating a file in a directory where your
            system looks for programs.
            This list is configured by setting the $PATH environment variable,
            for instance in your "~/.bashrc" file.
            ''').strip())
        info('')

        sys_paths = pathutils.get_system_executable_paths()
        accessible_paths = [path for path in sys_paths if path and os.access(path, os.W_OK)]

        how_to_add_path = textwrap.dedent(
            '''\
            Assuming you use the bash shell (the default for most distros), create
            a directory called "~/bin" like this:

                mkdir ~/bin

            Now edit the file called ".bashrc" in your home directory and add this
            like at the very end:

                PATH="~/bin:$PATH"

            Close the terminal, open a new one and re-run this Karton command.
            ''').strip()

        if not accessible_paths:
            die(textwrap.dedent(
                '''\
                There's no directory in yout $PATH which is writable, so an alias
                cannot be created.
                ''') +
                how_to_add_path)

        info(textwrap.dedent(
            '''\
            These are the directories which can be used at the moment:
            ''').strip())

        for i, path in enumerate(accessible_paths):
            info(' - [%d] %s' % (i + 1, path))
        info(' - [Q] Quit')
        info('')

        while True:
            answer = raw_input('Which directory do you want to use for aliases? '
                               '[1 to %d or "Q" to quit] ' %
                               len(accessible_paths))
            answer = answer.lower()
            if answer == 'q':
                die(textwrap.dedent(
                    '''\
                    Alias directory not configured.

                    If you quit because none of the displayed directories is suitable, you
                    can add a new directory to your shell's configuration file.
                    ''') +
                    how_to_add_path)

            choice = None
            try:
                answer = int(answer)
                if answer >= 1:
                    choice = accessible_paths[answer - 1]
            except (ValueError, IndexError):
                pass

            if choice is not None:
                return choice


    @staticmethod
    def _print_alias(alias):
        '''
        Print information about `alias`.

        alias
            The `configuration.ImageAlias` to analyse.
        '''
        if alias.implied_command:
            extra = ' (the "%s" command is used automatically)' % alias.implied_command
        else:
            extra = ''

        info('"%s" is an alias for "%s"%s.' % (alias.alias_name, alias.image_name, extra))
