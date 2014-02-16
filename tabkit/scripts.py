import sys
import argparse
from itertools import islice, izip, tee

from awk import map_program
from header import DataDesc, OrderField, parse_order
from utils import Files, xsplit
from exception import decorate_exceptions


def add_common_args(parser):
    parser.add_argument("-N", "--no-header", help="Don't output header", action="store_true")


def split_fields(string):
    return [field.strip() for field in string.split(",")]


@decorate_exceptions
def cat():
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
        sys.stdout.write(str(data_desc) + "\n")
        sys.stdout.flush()

    files.call(['cat'])


@decorate_exceptions
def cut():
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
        TabkitException("You must specify list of fields")

    files = Files(args.files)
    data_desc = files.data_desc()

    if args.fields:
        fields = split_fields(args.fields)

    elif args.remove:
        remove_fields = split_fields(args.remove)
        [data_desc.index(field) for field in remove_fields]  # check remove fields even exist
        fields = [name for name in data_desc.field_names if name not in remove_fields]

    field_indices = (data_desc.index(field) for field in fields)
    options = ['-f']
    options.append(",".join(str(index+1) for index in field_indices))

    order = []
    for order_key in data_desc.order:
        if not order_key.name in fields:
            break
        order.append(order_key)

    data_desc = DataDesc(
        fields=[f for f in data_desc if f.name in fields],
        order=order
    )

    if not args.no_header:
        sys.stdout.write(str(data_desc) + "\n")
        sys.stdout.flush()

    files.call(['cut'] + options)


@decorate_exceptions
def map():
    parser = argparse.ArgumentParser(
        add_help=True,
        description="Perform a map operation on the input"
    )
    parser.add_argument('files', metavar='FILE', type=argparse.FileType('r'), nargs="*")
    parser.add_argument('-a', '--all', action="store_true",
                        help="Add all fields to output (implied without -o option)")
    parser.add_argument('-o', '--output', action="append", help="Output fields", default=[])
    parser.add_argument('-f', '--filter', action="append", help="Filter expression")
    add_common_args(parser)

    args = parser.parse_args()
    files = Files(args.files)
    data_desc = files.data_desc()

    if args.all or not args.output:
        args.output.extend(f.name for f in data_desc)

    program, data_desc = map_program(data_desc, args.output, args.filter)

    if not args.no_header:
        sys.stdout.write(str(data_desc) + "\n")
        sys.stdout.flush()

    files.call(['awk', "-F", "\t", str(program)])


def make_order(keys):
    for key in keys:
        for order in parse_order(key):
            yield OrderField(*order)


@decorate_exceptions
def sort():
    parser = argparse.ArgumentParser(
        add_help=True,
        description="Write sorted concatenation of all FILE(s) to standard output."
    )
    parser.add_argument('files', metavar='FILE', type=argparse.FileType('r'), nargs="*")
    parser.add_argument('-k', '--keys', action="append", default=[],
                        help="List sorting keys as field[:(str|num|general)][:desc]")
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


@decorate_exceptions
def pretty():
    parser = argparse.ArgumentParser(
        add_help=True,
        description="Output FILE(s) as human-readable pretty table."
    )
    parser.add_argument('files', metavar='FILE', type=argparse.FileType('r'), nargs="*")
    parser.add_argument('-n', default=100, 
        help="Preread N rows to calculate column widths, default is 100") 

    args = parser.parse_args()
    files = Files(args.files)
    data_desc = files.data_desc()
    preread, rows = tee((row.rstrip("\n") for row in files), 2)

    # gather column widths
    widths = [len(str(f)) for f in data_desc]
    for row in islice(preread, args.n):
        for i, value in enumerate(xsplit(row)):
            widths[i] = max(widths[i], len(value))

    widths = [w + 2 for w in widths]
    print "|".join((" %s " % (f,)).ljust(w) for w, f in izip(widths, data_desc))
    print "+".join("-"*w for w in widths)
    for row in rows:
        print "|".join((" %s " % v).ljust(w) for w, v in izip(widths, xsplit(row)))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        script = sys.argv.pop(1)
        sys.argv[0] = script
        globals()[script]()
