#! /usr/bin/env python
#
# Copyright (C) 2016-2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

import logging

# For practicality.
from logging import die, info, verbose


def run_karton():
    '''
    Runs Karton.
    '''
    pass


def main():
    '''
    Runs Karton as a command, i.e. taking care or dealing with keyboard interrupts,
    unexpected exceptions, etc.

    If you need to run Karton as part of another program or from unit tests, use
    run_karton instead.
    '''

    try:
        run_karton()
    except KeyboardInterrupt:
        info('\nInterrupted.')
        raise SystemExit(1)
    except Exception as exc: # pylint: disable=broad-except
        # We print the backtrace only if verbose logging is enabled.
        msg = 'Internal error!\nGot exception: "%s".\n' % exc
        if logging.get_verbose():
            verbose(msg)
            raise
        else:
            die(msg)

    raise SystemExit(0)


if __name__ == '__main__':
    main()
