import sys
from functools import wraps


class TabkitException(Exception):
    pass


def handle_exceptions(f, stderr=None):
    stderr = stderr or sys.stderr
    try:
        return f()
    except TabkitException as e:
        print >> stderr, "%s: %s" % (sys.argv[0], e)


def decorate_exceptions(f, stderr=None):
    @wraps(f)
    def wrapper():
        return handle_exceptions(f, stderr)
    return wrapper

