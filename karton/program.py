#! /usr/bin/env python
#
# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import argparse
import collections
import os
import sys
import time
import textwrap

from . import (
    compat,
    alias,
    container,
    runtime,
    updater,
    version,
    )

from .log import die, info, verbose, get_verbose, set_verbose


class ArgumentParserError(Exception):
    '''
    An error raised while parsing arguments.
    '''
    pass


class ArgumentParser(argparse.ArgumentParser):
    '''
    `ArgumentParser` for handling special Karton use cases.
    '''

    def error(self, message):
        if message == 'too few arguments':
            # There seems to be no other way, but we need a decent message when
            # the program is invoked without arguments.
            message = '%s; try "%s help"' % (message, self.prog)

        super(ArgumentParser, self).error(message)


class SharedArgument(object):
    '''
    Definition of an argparse argument which can be added to multiple subparsers
    (AKA commands).
    '''

    def __init__(self, *args, **kwargs):
        '''
        Initialise a `SharedArgument`.

        The arguments are the same you would pass to `ArgumentParser.add_argument`.
        '''
        self.args = args
        self.kwargs = kwargs

    def add_to_parser(self, target_parser):
        '''
        Add the command to `target_parser`.
        '''
        target_parser.add_argument(*self.args, **self.kwargs)

    @staticmethod
    def add_group_to_parser(target_parser, shared_arguments):
        '''
        Add all the commands in the `shared_arguments` iterable to `target_parser`.

        target_parser:
            A parser to which `shared_arguments` should be added.
        shared_arguments:
            A list of `SharedArgument`.
        '''
        for arg in shared_arguments:
            arg.add_to_parser(target_parser)


class FakeParser(object):
    '''
    A parser-replacement object which does nothing (i.e. doesn't add options).

    This is used to simplify the code in case some commands are disabled.
    '''

    def __init__(self, *args, **kwargs):
        self.karton_main_command_name = None

    @staticmethod
    def add_argument(*args, **kwargs):
        return None

    def add_subparsers(self, *args, **kwargs):
        return self

    def add_parser(self, *args, **kwargs):
        return self


CommandInfo = collections.namedtuple('CommandInfo', ['name', 'subparser', 'callback'])


def do_run(parsed_args, image):
    if not parsed_args.remainder:
        raise ArgumentParserError('too few arguments')

    image.command_run(parsed_args.remainder, parsed_args.cd)


def do_shell(parsed_args, image):
    image.command_shell(parsed_args.cd)


def do_start(parsed_args, image):
    image.command_start()


def do_stop(parsed_args, image):
    image.command_stop(parsed_args.force)


def do_build(parsed_args, image):
    image.command_build(parsed_args.no_cache)


def do_status(parsed_args, image):
    if parsed_args.json:
        image.command_status_json()
    else:
        image.command_status()


def do_image_list(parsed_args, session):
    if parsed_args.json:
        container.Image.command_image_list_json(session.config)
    else:
        container.Image.command_image_list(session.config)


def do_image_create(parsed_args, session):
    container.Image.command_image_create(session.config,
                                         parsed_args.image_name,
                                         parsed_args.directory)


def do_image_import(parsed_args, session):
    container.Image.command_image_import(session.config,
                                         parsed_args.image_name,
                                         parsed_args.directory)


def do_image_remove(parsed_args, session):
    assert parsed_args.image_name

    image_config = session.config.image_with_name(parsed_args.image_name)
    if image_config is None:
        die('The image "%s" doesn\'t exist.' % parsed_args.image_name)

    image = container.Image(session, image_config)
    image.command_image_remove(parsed_args.force)


def do_alias(parsed_args, session):
    manager = alias.AliasManager(session.config)

    def check_implied_command():
        if parsed_args.implied_command:
            die('"--command" only makes sense when adding an alias.')

    def check_no_json():
        if parsed_args.json:
            die('"--json" can only be used when no positional argument is provided.')

    if parsed_args.remove:
        if not parsed_args.alias_name:
            die('If you specify "--remove" you must specify the alias you want to remove.')
        if parsed_args.image_name:
            die('If you specify "--remove" you cannot specify the image name, '
                'just the alias name.')

        check_implied_command()
        check_no_json()

        manager.command_remove(parsed_args.alias_name)

    elif parsed_args.alias_name is None:
        # The second positional argument cannot be non-None if the first is.
        assert parsed_args.image_name is None
        check_implied_command()

        if parsed_args.json:
            manager.command_show_all_json()
        else:
            manager.command_show_all()

    else:
        assert parsed_args.alias_name is not None
        check_no_json()

        allowed_implied_commands = (
            None,
            'run',
            'shell',
            'start',
            'stop',
            'status',
            'build',
            )
        if parsed_args.implied_command not in allowed_implied_commands:
            die('Command "%s" is not a valid command to use with an alias.' %
                parsed_args.implied_command)

        if parsed_args.image_name:
            manager.command_add(parsed_args.alias_name,
                                parsed_args.image_name,
                                parsed_args.implied_command)
        else:
            check_implied_command()
            manager.command_show(parsed_args.alias_name)


def run_karton(session, arguments):
    '''
    Runs Karton.

    session:
        A `runtime.Session` instance.
    arguments:
        Te command line arguments (for instance `sys.argv`).
    '''

    assert session

    # Check if we are run through an alias.
    program_name = os.path.basename(arguments[0])
    if program_name in ('karton.py', 'karton.pyc', 'karton.pyo'):
        program_name = 'karton'

    if program_name != 'karton':
        current_alias = session.config.get_alias(program_name)
    else:
        current_alias = None

    if current_alias:
        implied_image_name = current_alias.image_name
        if current_alias.implied_command is not None:
            arguments.insert(1, current_alias.implied_command)
    else:
        implied_image_name = None

    # And now setup the parser.
    parser = ArgumentParser(prog=program_name,
                            description='Manages semi-persistent Docker containers.')
    subparsers = parser.add_subparsers(dest='command', metavar='COMMAND')

    parser.add_argument(
        '--version',
        action='version',
        version='Karton %s' % version.__version__)

    all_commands = {}

    def add_command_internal(command_name, callback, *args, **kwargs):
        command_subparser = subparsers.add_parser(command_name, *args, **kwargs)
        all_commands[command_name] = CommandInfo(
            name=command_name,
            subparser=command_subparser,
            callback=callback)
        return command_subparser

    def add_command(command_name, callback, *args, **kwargs):
        add_even_if_not_image = kwargs.get('add_even_if_not_image')
        if add_even_if_not_image:
            del kwargs['add_even_if_not_image']

        if implied_image_name and not add_even_if_not_image:
            # Commands which do not operate on images are not supported if run throguh an
            # alias.
            return FakeParser()

        return add_command_internal(command_name, callback, *args, **kwargs)

    def add_image_command(command_name, image_callback, *args, **kwargs):
        def callback(callback_parsed_args, callback_session):
            assert session == callback_session
            assert parsed_args.image_name

            image_config = session.config.image_with_name(parsed_args.image_name)
            if image_config is None:
                die('The image "%s" doesn\'t exist.' % parsed_args.image_name)

            image = container.Image(session, image_config)
            image_callback(parsed_args, image)

        command_subparser = add_command_internal(command_name, callback, *args, **kwargs)

        if not implied_image_name:
            # We don't have an image name already (given through an alias), so we need to get
            # it on the command line.
            command_subparser.add_argument(
                'image_name',
                metavar='IMAGE-NAME',
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
        for command in compat.itervalues(all_commands):
            command.subparser.add_argument(*args, **kwargs)

    # Definition of arguments common to multiple commands.
    cd_args = (
        SharedArgument(
            '--no-cd',
            dest='cd',
            action='store_const',
            const=container.Image.CD_NO,
            default=container.Image.CD_YES,
            help='don\'t change the current directory in the image'),
        SharedArgument(
            '--auto-cd',
            dest='cd',
            action='store_const',
            const=container.Image.CD_AUTO,
            help='change the current directory in the image only if it\'s available '
            'in both image and host'),
        )

    json_arg = SharedArgument(
        '--json',
        action='store_true',
        help=argparse.SUPPRESS)

    # "run" command.
    run_parser = add_image_command(
        'run',
        do_run,
        help='run a  program inside the image',
        description='Runs a program or command inside the image (starting the image if '
        'necessary). '
        'Envionrment variable can preceed the command to run, for instance '
        '"karton run IMAGE-NAME VAR=VALUE COMMAND".')

    # This needs to be argparse.REMAINDER so options are passed down to the command
    # instead of being eaten by the karton command itself.
    # The side effect of this is that parsed_args.remainder may be empty.
    run_parser.add_argument(
        'remainder',
        metavar='COMMANDS',
        nargs=argparse.REMAINDER,
        help='commands to execute inside the image')

    SharedArgument.add_group_to_parser(run_parser, cd_args)

    # "shell" command.
    shell_parser = add_image_command(
        'shell',
        do_shell,
        help='start a shell inside the image',
        description='Starts an interactive shell inside the image (starting the image '
        'if necessary).')

    SharedArgument.add_group_to_parser(shell_parser, cd_args)

    # "start" command.
    add_image_command(
        'start',
        do_start,
        help='if not running, start the image',
        description='Starts the image. If already running does nothing. '
        'Usually you should not need to use this command as both "run" and "shell" start '
        'the image automatically.')

    # "stop" command.
    stop_command = add_image_command(
        'stop',
        do_stop,
        help='stop the image if running',
        description='Stops the image. If already not running does nothing. '
        'If there are commands running in the image, the user is asked before stopping the '
        'image. Pass "--force" to stop in any case without asking.')

    stop_command.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='stop the image without asking even if commands are running in it')

    # "status" command.
    status_parser = add_image_command(
        'status',
        do_status,
        help='query the status of the image',
        description='Prints information about the status of the image and the list of '
        'programs running in it.')

    json_arg.add_to_parser(status_parser)

    # "build" command.
    build_command = add_image_command(
        'build',
        do_build,
        help='build the image from its definition',
        description='Builds (or rebuilds) the image from its definition.')

    build_command.add_argument(
        '--no-cache',
        action='store_true',
        help='do not use the Docker cached data when building the image (thus rebuilding '
        'the image from scratch)')

    # "image" command.
    image_parser = add_command_with_sub_commands(
        'image',
        help='manage images',
        description='Manages the creation and deletion of images.')

    # "image list" command.
    image_list_parser = add_sub_command(
        image_parser,
        'list',
        do_image_list,
        help='list existing images',
        description='List all existing and configured images.')

    json_arg.add_to_parser(image_list_parser)

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

    # "image remove" command.
    image_remove_parser = add_sub_command(
        image_parser,
        'remove',
        do_image_remove,
        help='remove an existing image',
        description='Removes and existing image and its aliases, stopping it if it\'s running.')

    image_remove_parser.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='if there are running commands in the image, then they are stopped without asking')

    image_remove_parser.add_argument(
        'image_name',
        metavar='IMAGE-NAME',
        help='the name of the image to remove')

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
        '--command',
        dest='implied_command',
        help='if adding an alias, the alias will imply the specified command')

    alias_parser.add_argument(
        '--remove',
        action='store_true',
        help='remove the alias')

    json_arg.add_to_parser(alias_parser)

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
        add_even_if_not_image=True,
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
    parsed_args = parser.parse_args(arguments[1:])

    if getattr(parsed_args, 'verbose', None) is None:
        # This is needed in Python 3 if no argument is passed. Not sure why.
        parser.error('too few arguments')

    if implied_image_name:
        parsed_args.image_name = implied_image_name

    set_verbose(parsed_args.verbose)

    command = all_commands.get(parsed_args.command)
    if command is None:
        die('Invalid command "%s". This should not happen.' % parsed_args.command)

    # We don't use argparse's ability to call a callback as we need to do stuff before
    # it's called.
    try:
        command.callback(parsed_args, session)
    except ArgumentParserError as exc:
        parser.error(exc.message)


def main(session, arguments):
    '''
    Run Karton as a command, i.e. taking care or dealing with keyboard interrupts,
    unexpected exceptions, etc.

    This function doesn't return and raises a `SystemExit` with the appropriate
    exit code.

    If you need to run Karton as part of another program or from unit tests, use
    `run_karton` instead.

    session:
        A `runtime.Session` instance.
    arguments:
        The command line arguments (for instance `sys.argv`).
    '''

    now = int(time.time())
    seconds_in_a_week = 7 * 24 * 60 * 60
    time_for_a_check = now - session.config.last_update_check > seconds_in_a_week

    both_out_and_err_ttys = sys.stdout.isatty() and sys.stderr.isatty()

    if time_for_a_check and both_out_and_err_ttys:
        update_check = updater.Updater(
            'https://api.github.com/repos/karton/karton/releases',
            version.__version__)
    else:
        update_check = None

    exit_code = 0

    try:
        run_karton(session, arguments)
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
    except SystemExit as exc:
        exit_code = exc.code

    if update_check:
        did_check, new_version = update_check.results

        if new_version is not None:
            info(textwrap.dedent(
                '''\
                A new version of Karton is available! You can update from %(curr)s to %(new)s.
                If you installed Karton with pip, you can update it with:
                    pip install --upgrade --user karton
                ''').strip() % dict(
                    curr=version.__version__,
                    new=new_version,
                    ))
        else:
            verbose('No new version of Karton is available.')

        if did_check:
            verbose('Update check completed, it won\'t be re-run for a week.')
            session.config.last_update_check = now
        else:
            verbose('Update check not completed, it will be re-run at the next invocation.')
    else:
        verbose('No update check was run.')

    raise SystemExit(exit_code)


def main_with_defaults():
    '''
    Entry point for the script.

    Call `main` with a default session and `sys.argv`.
    '''
    main(runtime.Session.default_session(), sys.argv)
