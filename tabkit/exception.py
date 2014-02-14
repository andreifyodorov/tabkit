import sys
import types
from functools import wraps


class TabkitException(Exception):
    pass


def handle_exceptions(f, stderr=None, script=None):
    stderr = stderr or sys.stderr
    script = script or sys.argv[0]
    try:
        return f()
    except TabkitException as e:
        print >> stderr, "%s: %s" % (script, e)


def decorate_exceptions(f):
    @wraps(f)
    def wrapper():
        return handle_exceptions(f)
    return wrapper


def test_exception(f):
    def wrapper():
        result = f()
        if isinstance(result, types.GeneratorType):
            return list(result)
        return result
    return handle_exceptions(wrapper, stderr=sys.stdout, script="doctest")
