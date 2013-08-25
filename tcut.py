#!/usr/bin/python

import sys
import argparse
import subprocess

from tabkit.header import DataDesc
from tabkit.utils import Files, handle_exceptions, add_common_args

def split_fields(string):
    return [field.strip() for field in string.split(",")]

def main():
    parser = argparse.ArgumentParser(
        add_help=True, 
        description="Print selected columns from each FILE to standard output."
    )
    parser.add_argument('files', metavar='FILE', type=argparse.FileType('r'), nargs="*")
    parser.add_argument('-f', '--fields', help="Select only these fields")
    parser.add_argument('-r', '--remove', help="Remove these fields, keep the rest")
    add_common_args(parser)

    args = parser.parse_args()

    if not (args.fields or args.remove):
        Exception("You must specify list of fields")

    files = Files(args.files)

    data_desc = files.data_desc()

    if args.fields:
        fields = split_fields(args.fields)

    elif args.remove:
        remove_fields = split_fields(args.remove)
        [data_desc.index(field) for field in remove_fields] # check remove fields even exist
        fields = [name for name in data_desc.field_names if name not in remove_fields]

    field_indices = (data_desc.index(field) for field in fields)
    options = ['-f']
    options.append(",".join(str(index+1) for index in field_indices))

    data_desc = DataDesc(
        fields = [(name, type) for name, type in data_desc.fields if name in fields],
        order = None # TODO
    )

    if not args.no_header:
        print str(data_desc)

    subprocess.call(['cut'] + options + list(files.descriptors()))

if __name__ == "__main__":
#    handle_exceptions(main)
    main()