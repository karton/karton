#! /usr/bin/env python
#
# Copyright (C) 2017 Marco Barisione
#
# Released under the terms of the GNU LGPL license version 2.1 or later.

# This is a quick, hacky and poorly written script to generate some nice
# looking Markdown documentation for DefinitionProperties.

from __future__ import print_function

import re
import subprocess
import sys


START_PIPE = ' |  '

GENERAL = '__GENERAL__'
METHODS = 'Methods defined here:'
PROPS = 'Data descriptors defined here:'
OTHER = 'Data and other attributes defined here:'


def die(msg):
    if not msg.endswith('\n'):
        msg += '\n'
    sys.stderr.write(msg)
    raise SystemExit(1)


def generate_attribute(md_out, attr_name, attr_lines):
    if attr_name.startswith('_'):
        return

    attr_name_mangled = re.sub('self, *', '', attr_name)
    attr_name_mangled = re.sub(r'self\)', ')', attr_name_mangled)
    md_out.write('\n`%s`\n' % attr_name_mangled)
    md_out.write('-' * (len(attr_name_mangled) + 2) + '\n')

    inside_dl = False
    attr_lines_count = len(attr_lines)
    i = 0
    while i < attr_lines_count:
        line = attr_lines[i]
        i += 1

        if line.endswith(':'):
            arg_name = line[:-1]

            is_arg_or_return = False
            if arg_name == 'Return value':
                is_arg_or_return = True
            elif arg_name in attr_name:
                is_arg_or_return = True
                arg_name = '<code>%s</code>' % arg_name

            if is_arg_or_return:
                if not inside_dl:
                    md_out.write('<dl>\n')
                    inside_dl = True

                md_out.write('<dt>%s:</dt>\n' % arg_name)
                md_out.write('<dd>')
                while i < attr_lines_count:
                    arg_line = attr_lines[i]
                    if not arg_line.startswith(' ' * 4):
                        break
                    i += 1
                    arg_line = arg_line[4:]
                    arg_line = re.sub('`([a-zA-Z0-9_]+)`', r'<code>\1</code>', arg_line)
                    md_out.write(arg_line + '\n')
                md_out.write('</dd>\n')

                continue

        assert not inside_dl
        md_out.write(line + '\n')

    if inside_dl:
        md_out.write('</dl>\n')


def process(md_out_path):
    lines = subprocess.check_output([
        'python',
        '-c',
        'from karton import defprops; help(defprops.DefinitionProperties)',
        ]).strip().split('\n')

    while not lines[0].startswith(START_PIPE):
        lines.pop(0)

    sections = {
        GENERAL: [],
        METHODS: [],
        PROPS: [],
        OTHER: [],
        }

    current_section = sections[GENERAL]
    current_symbol = None
    current_symbol_name = None

    for line in lines:
        assert line.startswith(START_PIPE)
        line = line[len(START_PIPE):]

        if line in sections.keys():
            # Start a section.
            current_section = sections[line]
        elif line.startswith(' ' * 4):
            # Add stuff to an existing symbol.
            assert current_symbol is not None
            current_symbol.append(line[4:])
        elif not line and current_section is not sections[GENERAL]:
            # Empty line between symbols (the ones inside symbols actually have
            # some spaces in it).
            pass
        elif line == '-' * 70:
            # Separator, ignore it.
            pass
        else:
            # Add a new symbol.
            current_symbol_name = line.strip()
            current_symbol = []
            current_section.append((current_symbol_name, current_symbol))

    with open(md_out_path, 'w') as md_out:
        md_out.write('DefinitionProperties\n')
        md_out.write('====================\n\n')
        for general_line, _ in sections[GENERAL]:
            md_out.write(general_line + '\n')
        md_out.write('\n')

        for section in (METHODS, PROPS):
            for attr_name, attr_lines in sections[section]:
                generate_attribute(md_out, attr_name, attr_lines)


def main(argv):
    if len(argv) != 2:
        die('%s MARKDOWN_DOC_OUTPUT' % argv[0])

    process(argv[1])


if __name__ == '__main__':
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        die('\n\nInterrupted.')
