#! /usr/bin/env python
#
# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import argparse
import collections

import alias
import container
import runtime

from log import die, info, verbose, get_verbose, set_verbose


class ArgumentParser(argparse.ArgumentParser):
    '''
    ArgumentParser for handling special Karton use cases.
    '''

    def error(self, message):
        if message == 'too few arguments':
            # There seems to be no other way, but we need a decent message when
            # the program is invoked without arguments.
            self.print_help()
            raise SystemExit(1)

        super(ArgumentParser, self).error(message)


class SharedArgument(object):
    '''
    Definition of an argparse argument which can be added to multiple subparsers
    (AKA commands).
    '''

    def __init__(self, *args, **kwargs):
        '''
        Initialise a SharedArgument. The arguments are the same you would pass
        to ArgumentParser.add_argument.
        '''
        self.args = args
        self.kwargs = kwargs

    def add_to_parser(self, target_parser):
        '''
        Add the command to target_parser.
        '''
        target_parser.add_argument(*self.args, **self.kwargs)

    @staticmethod
    def add_group_to_parser(target_parser, shared_arguments):
        '''
        Add all the commands in the shared_arguments iterable to target_parser.
        '''
        for arg in shared_arguments:
            arg.add_to_parser(target_parser)


CommandInfo = collections.namedtuple('CommandInfo', ['name', 'subparser', 'callback'])


def do_run(parsed_args, image):
    image.command_run(parsed_args.remainder, parsed_args.cd)


def do_shell(parsed_args, image):
    image.command_shell(parsed_args.cd)


def do_start(parsed_args, image):
    image.command_start()


def do_stop(parsed_args, image):
    image.command_stop(parsed_args.force)


def do_build(parsed_args, image):
    image.command_build()


def do_status(parsed_args, image):
    image.command_status()


def do_image_create(parsed_args, session):
    container.Image.command_image_create(session.config,
                                         parsed_args.image_name,
                                         parsed_args.directory)


def do_image_import(parsed_args, session):
    container.Image.command_image_import(session.config,
                                         parsed_args.image_name,
                                         parsed_args.directory)


def do_alias(parsed_args, session):
    manager = alias.AliasManager(session.config)

    def check_no_run():
        if parsed_args.run:
            die('"--run" only makes sense when adding an alias.')

    if parsed_args.remove:
        if not parsed_args.alias_name:
            die('If you specify "--remove" you must specify the alias you want to remove.')
        if parsed_args.image_name:
            die('If you specify "--remove" you cannot specify the image name, '
                'just the alias name.')

        check_no_run()

        manager.command_remove(parsed_args.alias_name)

    elif parsed_args.alias_name is None:
        # The second positional argument cannot be non-None if the first is.
        assert parsed_args.image_name is None
        check_no_run()
        manager.command_show_all()

    else:
        assert parsed_args.alias_name is not None

        if parsed_args.image_name:
            manager.command_add(parsed_args.alias_name, parsed_args.image_name, parsed_args.run)
        else:
            check_no_run()
            manager.command_show(parsed_args.alias_name)


def run_karton(session):
    '''
    Runs Karton.

    session - a runtime.Session instance.
    '''

    assert session

    parser = ArgumentParser(description='Manages semi-persistent Docker containers.')
    subparsers = parser.add_subparsers(dest='command', metavar='COMMAND')

    all_commands = {}

    def add_command(command_name, callback, *args, **kwargs):
        command_subparser = subparsers.add_parser(command_name, *args, **kwargs)
        all_commands[command_name] = CommandInfo(
            name=command_name,
            subparser=command_subparser,
            callback=callback)
        return command_subparser

    def add_image_command(command_name, image_callback, *args, **kwargs):
        def callback(callback_parsed_args, callback_session):
            assert session == callback_session

            if parsed_args.image_name is None:
                die('You need to specify wich image to target with the "-i" option '
                    '(or the longer form, "--image").')

            image_config = session.config.image_with_name(parsed_args.image_name)
            if image_config is None:
                die('The image "%s" doesn\'t exist.' % parsed_args.image_name)

            image = container.Image(session, image_config)
            image_callback(parsed_args, image)

        command_subparser = add_command(command_name, callback, *args, **kwargs)

        command_subparser.add_argument(
            '-i',
            '--image',
            dest='image_name',
            help='name of the image to target')

        return command_subparser

    def add_command_with_sub_commands(main_command_name, *args, **kwargs):
        def do_sub_command(parsed_args, callback_session):
            assert callback_session == session

            joined_command = main_command_name + ' ' + parsed_args.sub_command
            sub_command = all_commands.get(joined_command)
            if sub_command is None:
                die('Invalid command "%s". This should not happen.' % joined_command)

            sub_command.callback(parsed_args, session)

        command_with_sub_commands = add_command(
            main_command_name,
            do_sub_command,
            *args,
            **kwargs)

        command_subparsers = command_with_sub_commands.add_subparsers(
            dest='sub_command',
            metavar='SUB-COMMAND')
        command_subparsers.karton_main_command_name = main_command_name

        return command_subparsers

    def add_sub_command(command_subparsers, sub_command_name, callback, *args, **kwargs):
        main_command_name = command_subparsers.karton_main_command_name
        joined_command = main_command_name + ' ' + sub_command_name

        sub_command_subparser = command_subparsers.add_parser(sub_command_name, *args, **kwargs)
        all_commands[joined_command] = CommandInfo(
            name=joined_command,
            subparser=sub_command_subparser,
            callback=callback)

        return sub_command_subparser

    def add_to_every_command(*args, **kwargs):
        for command in all_commands.itervalues():
            command.subparser.add_argument(*args, **kwargs)

    # Definition of arguments common to multiple commands.
    cd_args = (
        SharedArgument(
            '--no-cd',
            dest='cd',
            action='store_const',
            const=container.Image.CD_NO,
            default=container.Image.CD_YES,
            help='don\'t change the current directory in the container'),
        SharedArgument(
            '--auto-cd',
            dest='cd',
            action='store_const',
            const=container.Image.CD_AUTO,
            help='chanbge the current directory in the container only if the same is available ' \
                'in both container and host'),
        )

    # "run" command.
    run_parser = add_image_command(
        'run',
        do_run,
        help='run a  program in the container',
        description='Runs a program or command inside the container (starting it if necessary).')

    run_parser.add_argument(
        'remainder',
        metavar='COMMANDS',
        nargs=argparse.REMAINDER,
        help='commands to execute in the container')

    SharedArgument.add_group_to_parser(run_parser, cd_args)

    # "shell" command.
    shell_parser = add_image_command(
        'shell',
        do_shell,
        help='start a shell in the container',
        description='Starts an interactive shell inside the container (starting it if necessary)')

    SharedArgument.add_group_to_parser(shell_parser, cd_args)

    # "start" command.
    add_image_command(
        'start',
        do_start,
        help='if not running, start the container',
        description='Starts the container. If already running does nothing. '
        'Usually you should not need to use this command as both "run" and "shell" start '
        'the container automatically.')

    # "stop" command.
    stop_command = add_image_command(
        'stop',
        do_stop,
        help='stop the container if running',
        description='Stops the container. If already not running does nothing. '
        'If there are commands running in the container, the user is asked before stopping the '
        'container. Pass "--force" to stop in any case without asking.')

    stop_command.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='stop the container without asking even if commands are running in it')

    # "status" command.
    add_image_command(
        'status',
        do_status,
        help='query the status of the container',
        description='Prints information about the status of the container and the list of '
        'programs running in it.')

    # "build" command.
    add_image_command(
        'build',
        do_build,
        help='build the image for the container',
        description='Builds (or rebuilds) the image for the specified container.')

    # "image" command.
    image_parser = add_command_with_sub_commands(
        'image',
        help='manage images',
        description='Manages the creation and deletion of images.')

    # "image create" command.
    image_create_parser = add_sub_command(
        image_parser,
        'create',
        do_image_create,
        help='create a new image',
        description='Creates a new image, including generating a stub definition file.')

    image_create_parser.add_argument(
        'image_name',
        metavar='IMAGE-NAME',
        help='the name of the new image')

    image_create_parser.add_argument(
        'directory',
        metavar='EXISTING-PATH/NEW-IMAGE-DIRECTORY',
        help='the directory to create and where to put the definition file; '
             'the image directory must not exist, but the path leading to it must exist.')

    # "image import" command.
    image_create_parser = add_sub_command(
        image_parser,
        'import',
        do_image_import,
        help='create a new image by importing its definition from an existing one',
        description='Creates a new image by importing its definition from an existing directory.')

    image_create_parser.add_argument(
        'image_name',
        metavar='IMAGE-NAME',
        help='the name of the new image')

    image_create_parser.add_argument(
        'directory',
        metavar='EXISTING-IMAGE-DIRECTORY',
        help='the directory, containing a definition file and other needed files, to import')

    # "alias" command.
    alias_parser = add_command(
        'alias',
        do_alias,
        help='show or set aliases to avoid specifying the image every time',
        description='Shows or sets aliases. By using an alias you can invoke Karton without '
        'having to specify the name of the image every time.')

    alias_parser.add_argument(
        'alias_name',
        metavar='ALIAS-NAME',
        nargs='?',
        help='the name of the alias')

    alias_parser.add_argument(
        'image_name',
        metavar='IMAGE-NAME',
        nargs='?',
        help='the image to associate to the alias')

    alias_parser.add_argument(
        '--run',
        action='store_true',
        help='if adding an alias, the alias will imply the "run" command')

    alias_parser.add_argument(
        '--remove',
        action='store_true',
        help='remove the alias')

    # "help" command.
    def do_help(help_parsed_args, callback_session):
        command_name = ' '.join(help_parsed_args.topic)
        if not command_name:
            parser.print_help()
            return

        command = all_commands.get(command_name)
        if command is None:
            die('"%s" is not a Karton command. '
                'Try "karton help" to list the available commands.' % command_name)

        command.subparser.print_help()

    help_parser = add_command(
        'help',
        do_help,
        help='show the help message',
        description='Shows the documentation. If used with no argument, then the general '
        'documentation is shown. Otherwise, when a command is specified as argument, '
        'the documentation for that command is shown.')

    help_parser.add_argument(
        'topic',
        metavar='COMMAND',
        nargs=argparse.REMAINDER,
        help='command you want to know more about')

    # Arguments common to everything.
    add_to_every_command(
        '-v',
        '--verbose',
        action='store_true',
        help='enable verbose logging')

    # Now actually parse the command line.
    parsed_args = parser.parse_args()

    set_verbose(parsed_args.verbose)

    command = all_commands.get(parsed_args.command)
    if command is None:
        die('Invalid command "%s". This should not happen.' % parsed_args.command)

    # We don't use argparse's ability to call a callback as we need to do stuff before
    # it's called.
    command.callback(parsed_args, session)


def main(session):
    '''
    Runs Karton as a command, i.e. taking care or dealing with keyboard interrupts,
    unexpected exceptions, etc.

    If you need to run Karton as part of another program or from unit tests, use
    run_karton instead.

    session - a runtime.Session instance.
    '''

    try:
        run_karton(session)
    except KeyboardInterrupt:
        info('\nInterrupted.')
        raise SystemExit(1)
    except Exception as exc:
        # We print the backtrace only if verbose logging is enabled.
        msg = 'Internal error!\nGot exception: "%s".\n' % exc
        if get_verbose():
            verbose(msg)
            raise
        else:
            die(msg)

    raise SystemExit(0)


if __name__ == '__main__':
    main(runtime.Session.default_session())
