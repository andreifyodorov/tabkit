import os
import sys
import subprocess
from pipes import quote

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
                    this_data_desc.order = None # for more than two files cated together order is meaningless
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
