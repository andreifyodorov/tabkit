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
#    parser.add_argument('-f', '--filter', help="Filter expression")
    parser.add_argument('-o', '--output', help="Output fields")
    add_common_args(parser)

    args = parser.parse_args()

    files = Files(args.files)

    data_desc = files.data_desc()

    program, data_desc = map_program(data_desc, args.output)

    if not args.no_header:
        sys.stdout.write(str(data_desc) + "\n")
        sys.stdout.flush()

    files.call(['awk', "-F", "\t", str(program)])

if __name__ == "__main__":
    handle_exceptions(main)