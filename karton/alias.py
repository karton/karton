# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

#from log import die, verbose


import configuration

from log import die, info, verbose


class AliasManager(object):
    '''
    Deals with adding, removing and listing aliases.

    Aliases are used to access Karton without having to specify an image every time.

    All the methods starting with "command_" deal with expected exceptions
    (by calling log.die if needed) and are suitable to be called by a command
    line tool.
    '''

    def __init__(self, config):
        '''
        Initializes a AliasManager instance.

        config - a configuration.GlobalConfing instance used to store the aliases and
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

    def command_show(self, alias_name):
        '''
        Print information about the alias with name alias_name.

        alias_name - the name of the alias
        '''
        aliases = self._config.get_aliases()
        try:
            alias = aliases[alias_name]
        except KeyError:
            die('"%s" is not a known alias')

        self._print_alias(alias)

    def command_add(self, alias_name, image_name, run):
        '''
        Add an alias.

        alias_name - the name of the alias to add.
        image_name - the name of the image the alias should use.
        run - whether the alias should automatically call the "run" command.
        '''
        verbose('Adding alias "%s" for image "%s" (run=%s)' %
                (alias_name, image_name, run))

        image = self._config.image_with_name(image_name)
        if image is None:
            die('Cannot add alias "%s" for image "%s" as the image does not exist.' %
                (alias_name, image_name))

        alias = configuration.ImageAlias(alias_name, image_name, run)
        if not self._config.add_alias(alias):
            die('Cannot add alias "%s" for image "%s" as an alias with the same name already '
                'exists.' %
                (alias_name, image_name))

    def command_remove(self, alias_name):
        '''
        Remove an alias with name alias_name.

        alias_name - the name of the alias to remove.
        '''
        if not self._config.remove_alias(alias_name):
            die('Cannot remove the alias "%s" as it does not exist.' % alias_name)

    @staticmethod
    def _print_alias(alias):
        '''
        Print information about alias.

        alias - The configuration.ImageAlias to analyse.
        '''
        if alias.run:
            extra = ' (the "run" command is used automatically)'
        else:
            extra = ''

        info('"%s" is an alias for "%s"%s.' % (alias.alias_name, alias.image_name, extra))
