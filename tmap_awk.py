#!/usr/bin/python

import sys
import argparse
from tabkit.awk import map_program
from tabkit.exception import handle_exceptions
from tabkit.utils import add_common_args, Files

def main():
    parser = argparse.ArgumentParser(
        add_help=True, 
        description="Perform a map operation on the input"
    )
    parser.add_argument('files', metavar='FILE', type=argparse.FileType('r'), nargs="*")
    parser.add_argument('-a', '--all', action="store_true", help="Add all fields to output")
    parser.add_argument('-o', '--output', action="append", help="Output fields")
    parser.add_argument('-f', '--filter', action="append", help="Filter expression")
    add_common_args(parser)

    args = parser.parse_args()

    files = Files(args.files)

    data_desc = files.data_desc()

    if args.all:
        args.output.extend(f.name for f in data_desc.fields)

    program, data_desc = map_program(data_desc, args.output, args.filter)

    if not args.no_header:
        sys.stdout.write(str(data_desc) + "\n")
        sys.stdout.flush()

    files.call(['awk', "-F", "\t", str(program)])

if __name__ == "__main__":
    handle_exceptions(main)