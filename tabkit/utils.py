import os
import sys
import subprocess
from pipes import quote
from itertools import izip

from header import parse_header, generic_data_desc
from exception import TabkitException


def add_common_args(parser):
    parser.add_argument("-N", "--no-header", help="Don't output header", action="store_true")


class File(object):
    def __init__(self, fd):
        self.fd = fd
        self.name = fd.name

    def descriptor(self):
        return "/dev/fd/%d" % (self.fd.fileno(),)


class RegularFile(File):
    def header(self):
        return self.fd.readline().rstrip()

    def descriptor(self):
        os.lseek(self.fd.fileno(), 0, os.SEEK_SET)
        return "<( tail -n+2 %s )" % (super(RegularFile, self).descriptor(),)


class StreamFile(File):
    def _read_header(self):
        while True:
            c = os.read(self.fd.fileno(), 1)
            if c is None or c == "\n":
                return
            yield c

    def header(self):
        return "".join(self._read_header())


def file_obj(fd):
    try:
        fd.tell()
        return RegularFile(fd)
    except IOError:
        return StreamFile(fd)


class Files(object):
    def __init__(self, files=None):
        files = files or [sys.stdin]
        self.files = [file_obj(f) for f in files]

    def data_desc(self):
        data_desc = None
        for f in self.files:
            try:
                this_data_desc = parse_header(f.header())
                if data_desc:
                    # for more than two files being cated together order is meaningless
                    this_data_desc.order = None
                    data_desc = generic_data_desc(data_desc, this_data_desc)
                else:
                    data_desc = this_data_desc
            except TabkitException as e:
                raise TabkitException("%s in file '%s'" % (e, f.name))
        return data_desc

    def descriptors(self):
        return (f.descriptor() for f in self.files)

    def call(self, args):
        cmd = (
            "LC_ALL=C "
            + args.pop(0)
            + " " + " ".join(quote(arg) for arg in args)
            + " " + " ".join(self.descriptors())
        )
        subprocess.call(['bash', '-o', 'pipefail', '-o', 'errexit', '-c', cmd])


def xsplit(s, delim="\t"):
    """
    >>> list(xsplit("1 234 5", ' '))
    ['1', '234', '5']
    """
    start = 0
    while True:
        pos = s.find(delim, start)
        if pos < 0:
            yield s[start:]
            return
        yield s[start:pos]
        start = pos + 1


class parse_file(object):
    r'''
    >>> file = [
    ...     '# a:int, b:float, c',
    ...     '1',
    ...     '1\t2',
    ...     '1\t2\t3\t4'
    ... ]

    >>> p = parse_file(file)

    >>> str(p.data_desc)
    '# a:int\tb:float\tc'

    >>> next(p)
    DataRow(a=1, b=0.0, c='')

    >>> next(p)
    DataRow(a=1, b=2.0, c='')

    >>> next(p)
    DataRow(a=1, b=2.0, c='3')

    >>> from exception import test_exception
    >>> test_exception(lambda: list(parse_file(file, strict=True)))
    doctest: Line 2 contains 1 columns, whereas 3 columns expected
    '''

    def __init__(self, stream, strict=False):
        stream = iter(stream)
        self.data_desc = parse_header(next(stream).rstrip())

        def parse():
            RowClass = self.data_desc.row_class()
            rowlen = len(self.data_desc)
            for lineno, line in enumerate(stream):
                raw = xsplit(line.rstrip("\n"))
                values = [f.type(v) for v, f in izip(raw, self.data_desc.fields)]
                if len(values) != rowlen:
                    if strict:
                        raise TabkitException(
                            'Line %d contains %d columns, whereas %d columns expected' %
                            (lineno + 2, len(values), rowlen)
                        )
                    if len(values) > rowlen:  # truncate if longer
                        values = values[:rowlen]
                    if len(values) < rowlen:  # pad if shorter
                        values += [type() for name, type in self.data_desc.fields[len(values):]]
                yield RowClass(*values)

        self.iterator = parse()

    def __iter__(self):
        return self.iterator

    def next(self):
        return next(self.iterator)


def _str(value):  # dump True/False as 1/0 for lapidarity reasons
    if value is True:
        return '1'
    if value is False:
        return '0'
    return str(value)


class Writer(object):
    r'''
    >>> from StringIO import StringIO
    >>> from exception import test_exception

    >>> write = Writer(StringIO(), parse_header("# a:int, b:str, x:bool"))
    >>> write(a=1, b="banana", x=False)
    >>> write(b=10, x='True')
    >>> print write.fh.getvalue() # doctest: +NORMALIZE_WHITESPACE
    # a:int b       x:bool
      1     banana  0
            10      True

    >>> test_exception(lambda: write(a='0', b=10, c='True'))
    doctest: Unexpected field 'c'

    >>> write = Writer(StringIO(), parse_header("# a:int, b:str, x:bool"), strict=True)
    >>> test_exception(lambda: write(b=10, x='True'))
    doctest: Field 'a' required

    >>> test_exception(lambda: write(a="banana"))
    doctest: Value convertable to type int expected in field 'a', but got 'banana'

    >>> write(a="1", b="banana", x=0)
    >>> print write.fh.getvalue() # doctest: +NORMALIZE_WHITESPACE
    # a:int b       x:bool
      1     banana  0
    '''

    def __init__(self, fh, data_desc, strict=False):
        self.fh = fh
        self.data_desc = data_desc
        self.fh.write(str(data_desc) + "\n")
        if strict:
            self._get_values = self._get_values_strict

    def _get_values_strict(self, kwargs):
        for name, type in self.data_desc.fields:
            if name not in kwargs:
                raise TabkitException("Field %r required" % name)
            value = kwargs.pop(name)
            try:
                type(value)
            except (TypeError, ValueError) as e:
                raise TabkitException(
                    "Value convertable to type %s expected in field %r, but got %r" %
                    (type.__name__, name, value))
            yield _str(value)

    def _get_values(self, kwargs):
        for name in self.data_desc.field_names:
            yield _str(kwargs.pop(name, ''))

    def __call__(self, **kwargs):
        self.fh.write("%s\n" % "\t".join(self._get_values(kwargs)))
        if kwargs:
            raise TabkitException('Unexpected field %r' % kwargs.keys().pop())
