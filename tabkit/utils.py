import os
import sys
import subprocess
from pipes import quote
from itertools import izip, chain

from header import parse_header, generic_data_desc
from exception import TabkitException


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

    def __iter__(self):
        return chain.from_iterable(f.fd for f in self.files)

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
    >>> from exception import test_exception
    >>> file = [
    ...     '# a:int, b:float, c',
    ...     '1',
    ...     '1\t2',
    ...     '1\t2\t3\t4',
    ...     'a'
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

    >>> test_exception(lambda: next(p))
    doctest: Invalid literal for int() with base 10: 'a' at line 5

    >>> test_exception(lambda: list(parse_file(file, strict=True)))
    doctest: Found 1 columns, whereas 3 columns expected at line 2
    '''

    def __init__(self, stream, strict=False, data_desc=None):
        stream = iter(stream)
        self.data_desc = data_desc or parse_header(next(stream).rstrip())

        def parse():
            RowClass = self.data_desc.row_class()
            rowlen = len(self.data_desc)
            try:
                for lineno, line in enumerate(stream):
                    raw = xsplit(line.rstrip("\n"))
                    try:
                        values = [f.type(v) for v, f in izip(raw, self.data_desc)]
                    except ValueError as e:
                        raise TabkitException(str(e).capitalize())
                    if len(values) != rowlen:
                        if strict:
                            raise TabkitException(
                                'Found %d columns, whereas %d columns expected' %
                                (len(values), rowlen)
                            )
                        if len(values) > rowlen:  # truncate if longer
                            values = values[:rowlen]
                        if len(values) < rowlen:  # pad if shorter
                            values += [f.type() for f in self.data_desc.fields[len(values):]]
                    yield RowClass(*values)
            except (TabkitException) as e:
                raise TabkitException('%s at line %d' % (e, lineno + 2))

        self._iterator = parse()

    def __iter__(self):
        return self

    def next(self):
        return next(self._iterator)


def _str(value):  # dump True/False as 1/0 for lapidarity reasons
    if value is True:
        return '1'
    if value is False:
        return '0'
    if value is None:
        return ''
    return str(value)


def Writer(fh, data_desc, strict=False):
    if strict:
        return StrictWriter(fh, data_desc)
    else:
        return LooseWriter(fh, data_desc)


class WriterBase(object):
    def __init__(self, fh, data_desc):
        self.fh = fh
        self.data_desc = data_desc
        self.fh.write(str(data_desc) + "\n")


class StrictWriter(WriterBase):
    r'''
    >>> from StringIO import StringIO
    >>> from exception import test_exception

    >>> write = StrictWriter(StringIO(), parse_header("# a:int, b:str, x:bool"))
    >>> test_exception(lambda: write(b=10, x='True'))
    doctest: Field 'a' required

    >>> test_exception(lambda: write(a="banana"))
    doctest: Value convertable to type int expected in field 'a', but got 'banana'

    >>> write(a="1", b="banana", x=0)
    >>> print write.fh.getvalue() # doctest: +NORMALIZE_WHITESPACE
    # a:int b       x:bool
      1     banana  0
    '''
    def _get_values(self, kwargs):
        for field in self.data_desc:
            if field.name not in kwargs:
                raise TabkitException("Field %r required" % field.name)
            value = kwargs.pop(field.name)
            try:
                field.type(value)
            except (TypeError, ValueError) as e:
                raise TabkitException(
                    "Value convertable to type %s expected in field %r, but got %r" %
                    (field.type.__name__, field.name, value))
            yield _str(value)

    def __call__(self, **kwargs):
        self.fh.write("%s\n" % "\t".join(self._get_values(kwargs)))
        if kwargs:
            raise TabkitException('Unexpected field %r' % kwargs.keys().pop())


class LooseWriter(WriterBase):
    r'''
    >>> from StringIO import StringIO
    >>> from exception import test_exception

    >>> write = LooseWriter(StringIO(), parse_header("# a:int, b:str, x:bool"))
    >>> write(a=1, b="banana", x=False)
    >>> write(b=10, x='True')
    >>> print write.fh.getvalue() # doctest: +NORMALIZE_WHITESPACE
    # a:int b       x:bool
      1     banana  0
            10      True

    >>> test_exception(lambda: write(c='True'))
    '''

    def _get_values(self, kwargs):
        for name in self.data_desc.field_names:
            yield _str(kwargs.pop(name, ''))

    def __call__(self, **kwargs):
        self.fh.write("%s\n" % "\t".join(self._get_values(kwargs)))
