import sys
import argparse
from itertools import islice, izip, izip_longest, tee, chain

from .awk import map_program, grp_program
from .header import Field, DataDesc, OrderField, parse_order
from .exception import TabkitException, decorate_exceptions
from .type import generic_type, narrowest_type
from .utils import Files, xsplit


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
        sys.stdout.write("%s\n" % data_desc)
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
    options.append(",".join(str(index + 1) for index in field_indices))

    order = []
    for order_key in data_desc.order:
        if order_key.name not in fields:
            break
        order.append(order_key)

    data_desc = DataDesc(
        fields=[f for f in data_desc if f.name in fields],
        order=order
    )

    if not args.no_header:
        sys.stdout.write("%s\n" % data_desc)
        sys.stdout.flush()

    files.call(['cut'] + options)


@decorate_exceptions
def map():
    parser = argparse.ArgumentParser(
        add_help=True,
        description="Perform a map operation on all FILE(s)"
                    "and write result to standard output."
    )
    parser.add_argument('files', metavar='FILE', type=argparse.FileType('r'), nargs="*")
    parser.add_argument('-a', '--all', action="store_true",
                        help="Add all fields to output (implied without -o option)")
    parser.add_argument('-o', '--output', action="append", help="Output fields", default=[])
    parser.add_argument('-f', '--filter', action="append", help="Filter expression")
    parser.add_argument('-v', '--verbose', action="store_true", help="Verbose awk code")
    add_common_args(parser)

    args = parser.parse_args()
    files = Files(args.files)
    data_desc = files.data_desc()

    # if args.all or not args.output:
    #     args.output.extend(f.name for f in data_desc)
    #
    program, data_desc = map_program(data_desc, args.output, args.filter)

    if args.verbose:
        sys.stderr.write("%s\n" % program)

    if not args.no_header:
        sys.stdout.write("%s\n" % data_desc)
        sys.stdout.flush()

    files.call(['awk', "-F", "\t", '-v', 'OFS=\t', str(program)])


@decorate_exceptions
def group():
    parser = argparse.ArgumentParser(
        add_help=True,
        description="Perform a group operation on all FILE(s)"
                    "and write result to standard output."
    )
    parser.add_argument('files', metavar='FILE', type=argparse.FileType('r'), nargs="*")
    parser.add_argument('-g', '--group', action="append", help="Group fields", default=[])
    parser.add_argument('-o', '--output', action="append", help="Output fields", default=[])
    parser.add_argument('-v', '--verbose', action="store_true", help="Verbose awk code")
    add_common_args(parser)

    args = parser.parse_args()
    files = Files(args.files)
    data_desc = files.data_desc()

    if not args.group:
        args.group = ["_fake_implicit_group=1"]
    if args.output:
        TabkitException("You must specify list of output field")

    program, data_desc = grp_program(data_desc, args.group, args.output)

    if args.verbose:
        sys.stderr.write("%s\n" % program)

    if not args.no_header:
        sys.stdout.write("%s\n" % data_desc)
        sys.stdout.flush()

    files.call(['awk', "-F", "\t", '-v', 'OFS=\t', str(program)])


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
        sys.stdout.write("%s\n" % data_desc)
        sys.stdout.flush()

    files.call(['sort'] + options)


class add_set(argparse.Action):
    def __call__(self, parser, namespace, values, option_string):
        dest = getattr(namespace, self.dest)
        if not dest:
            setattr(namespace, self.dest, {values})
        else:
            dest.add(values)
            setattr(namespace, self.dest, dest)


@decorate_exceptions
def join():
    parser = argparse.ArgumentParser(
        add_help=True,
        description="Perform the join operation on LEFT_FILE and RIGHT_FILE "
                    "and write result to standard output."
    )
    parser.add_argument('left', metavar='LEFT_FILE', type=argparse.FileType('r'))
    parser.add_argument('right', metavar='RIGHT_FILE', type=argparse.FileType('r'))
    parser.add_argument('-j', '--join-key', metavar="FIELD",
                        help="Join on the FIELD of both LEFT_FILE and RIGHT_FILE")
    parser.add_argument('-1', '--left-key', metavar="FIELD",
                        help="Join on the FIELD of LEFT_FILE")
    parser.add_argument('-2', '--right-key', metavar="FIELD",
                        help="Join on the FIELD of RIGHT_FILE")
    parser.add_argument('-a', '--add-unpairable',
                        metavar="FILENO", type=int, default=set(), choices={1, 2}, action=add_set,
                        help="Add unpairable lines from FILENO")
    parser.add_argument('-v', '--only-unpairable',
                        metavar="FILENO", type=int, default=set(), choices={1, 2}, action=add_set,
                        help="Suppress all but unpairable lines from FILENO")
    parser.add_argument('-e', '--empty', metavar="NULL",
                        help="Fill unpairable fields with NULL (default is empty string)")
    # square brackets in metavare cause assertion error http://bugs.python.org/issue11874
    parser.add_argument('-o', '--output', metavar="FILENO.FIELD, ...",
                        help="Specify output fields. FILENO is optional if FIELD is unambiguous.")
    add_common_args(parser)
    args = parser.parse_args()

    left, right = args.left, args.right
    files = Files([left, right])
    left_desc, right_desc = list(files.data_descs())

    if not (args.join_key or (args.left_key and args.right_key)):
        raise TabkitException('Specify join field through -j or -1, -2 options')
    left_key = right_key = args.join_key
    if args.left_key:
        left_key = args.left_key
    if args.right_key:
        right_key = args.right_key

    if args.add_unpairable and args.only_unpairable:
        raise TabkitException(
            "-a does nothing in presence of -v. Are you sure about what you're trying to express?")

    output = []
    output_desc = []
    output_order = []
    generic_key = None
    if not args.only_unpairable or len(args.only_unpairable) == 2:
        if args.add_unpairable == {1}:
            # all keys from left table
            type_ = left_desc.get_field(left_key).type
        elif args.add_unpairable == {2}:
            # all keys from right table
            type_ = right_desc.get_field(right_key).type
        elif args.add_unpairable or args.only_unpairable:
            # all keys from both tables
            type_ = generic_type(left_desc.get_field(left_key).type,
                                 right_desc.get_field(right_key).type)
        else:
            # matching keys from both tables
            type_ = narrowest_type(left_desc.get_field(left_key).type,
                                   right_desc.get_field(right_key).type)
        generic_key = Field(left_key, type_)

    for fileno, file, key, desc in ((1, left, left_key, left_desc),
                                    (2, right, right_key, right_desc)):
        if key not in desc:
            raise TabkitException("No such field %r in file %r" % (key, file.name))
        try:
            field, field_type, order = desc.order.pop(0)  # remove it
            if not (field == key and field_type == "str" and not order):
                raise ValueError
        except (IndexError, ValueError):
            raise TabkitException(
                "File %r must be sorted lexicographicaly ascending by the field %r" %
                (file.name, key))
        if not args.output:
            if args.only_unpairable and fileno not in args.only_unpairable:
                continue
            for fieldno, field in enumerate(desc, start=1):
                if field.name == key:
                    if generic_key:
                        if file == left:
                            output.append("0")
                            output_desc.append(generic_key)
                            output_order.append(OrderField(field.name))
                        continue
                    elif fileno in args.only_unpairable:
                        output_order.append(OrderField(field.name))

                output.append("%d.%d" % (fileno, fieldno))
                if field in output_desc:
                    raise TabkitException(
                        "Duplicate field %r in file %r" % (field.name, file.name))
                output_desc.append(field)

    if args.output:
        for field in split_fields(args.output):
            if '.' in field:
                fileno, field_name = field.split('.', 1)
                try:
                    fileno = int(fileno)
                    if fileno not in [1, 2]:
                        raise ValueError
                except ValueError:
                    raise TabkitException('Bad output field format %r' % field)
                desc = (left_desc, right_desc)[fileno - 1]
                if field_name not in desc:
                    raise TabkitException('Unknown output field %r' % field)
                output.append("%d.%d" % (fileno, desc.index(field_name) + 1))
                output_desc.append(desc.get_field(field_name))
            else:
                if generic_key and field == generic_key.name:
                    output.append("0")
                    output_desc.append(generic_key)
                else:
                    if field in left_desc and field in right_desc:
                        raise TabkitException('Output field %r is ambiguous' % field)
                    if field in left_desc:
                        pass
                    elif field in right_desc:
                        pass
                    else:
                        raise TabkitException('Unknown output field %r' % field)

    output_field_names = {f.name for f in output_desc}
    output_order.extend(
        f for f in chain(left_desc.order, right_desc.order) if f.name in output_field_names)
    output_desc = DataDesc(output_desc, output_order)

    options = ['-1', str(left_desc.index(left_key) + 1),
               '-2', str(right_desc.index(right_key) + 1)]
    for fileno in args.add_unpairable:
        options.extend(['-a', str(fileno)])
    for fileno in args.only_unpairable:
        options.extend(['-v', str(fileno)])
    if args.empty:
        options.extend(['-e', args.empty])
    options.extend(['-o', ','.join(output)])

    if not args.no_header:
        sys.stdout.write("%s\n" % output_desc)
        sys.stdout.flush()

    files.call(['join', '-t', "\t"] + options)


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

    nfields = len(data_desc)
    split = lambda row: islice(xsplit(row), nfields)

    # gather column widths
    widths = [len(str(f)) for f in data_desc]
    for row in islice(preread, args.n):
        for i, value in enumerate(split(row)):
            widths[i] = max(widths[i], len(value))

    widths = [w + 2 for w in widths]
    print "|".join((" %s " % (f,)).ljust(w) for w, f in izip(widths, data_desc))
    print "+".join("-" * w for w in widths)
    for row in rows:
        print "|".join(
            (" %s " % (v or '')).ljust(w or 0)
            for w, v in izip_longest(widths, split(row))
        )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        script = sys.argv.pop(1)
        sys.argv[0] = script
        globals()[script]()
