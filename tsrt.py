#!/usr/bin/env python

import sys
import argparse

from tabkit.header import parse_order, OrderField, DataDesc
from tabkit.utils import Files, add_common_args
from tabkit.exception import TabkitException, handle_exceptions

def make_order(keys):
    for key in keys:
        for order in parse_order(key):
            yield OrderField(*order)

def main():
    parser = argparse.ArgumentParser(
        add_help=True, 
        description="Write sorted concatenation of all FILE(s) to standard output."
    )
    parser.add_argument('files', metavar='FILE', type=argparse.FileType('r'), nargs="*")
    parser.add_argument('-k', '--keys', action="append", default=[], help="List sorting keys as field[:(str|num|general)][:desc]")
    add_common_args(parser)

    args = parser.parse_args()

    files = Files(args.files)

    data_desc = files.data_desc()

    order = list(make_order(args.keys or data_desc.field_names))

    data_desc = DataDesc(
        fields=data_desc.fields,
        order=order
    )

    options = []
    for order in data_desc.order:
        option = "-k{0},{0}".format(data_desc.index(order.name) + 1)
        if order.type != 'str':
            option += order.type[0]
        if order.desc:
            option += "r"
        options.append(option)

    if not args.no_header:
        sys.stdout.write(str(data_desc) + "\n")
        sys.stdout.flush()

    files.call(['sort'] + options)

if __name__ == "__main__":
    handle_exceptions(main)