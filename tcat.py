#!/usr/bin/python

import sys
import argparse

from tabkit.header import DataDesc
from tabkit.utils import Files, add_common_args
from tabkit.exception import handle_exceptions

def split_fields(string):
    return [field.strip() for field in string.split(",")]

def main():
    parser = argparse.ArgumentParser(
        add_help=True, 
        description="Concatenate FILE(s), or standard input, to standard output."
    )
    parser.add_argument('files', metavar='FILE', type=argparse.FileType('r'), nargs="*")
    add_common_args(parser)

    args = parser.parse_args()

    files = Files(args.files)

    data_desc = files.data_desc()

    if not args.no_header:
        print str(data_desc)

    files.call(['cat'])

if __name__ == "__main__":
    handle_exceptions(main)