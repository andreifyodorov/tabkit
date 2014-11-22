from collections import namedtuple

from .exception import TabkitException


def parse_boolean(x=None):
    if x == "0":
        return False
    return bool(x)


TabkitTypesClass = namedtuple('TabkitTypesClass', 'str float int bool')

TabkitTypes = TabkitTypesClass(
    str=str,
    float=float,
    int=int,
    bool=parse_boolean
)

type_names = {type_: name for name, type_ in TabkitTypes._asdict().iteritems()}


def parse_type(type_str):
    type_str = type_str or 'str'
    type_ = getattr(TabkitTypes, type_str, None)
    if not type_:
        raise TabkitException("Unknown type '%s'" % type_str)
    return type_


def type_name(type_):
    name = type_names.get(type_)
    if not name:
        raise TabkitException("Uknown object '%r' passed as type" % type_)
    return name


type_hierarchy = (TabkitTypes.str, TabkitTypes.float, TabkitTypes.int, TabkitTypes.bool)


def generic_type(*types):
    return next(t for t in type_hierarchy if t in types)


def narrowest_type(*types):
    return next(t for t in reversed(type_hierarchy) if t in types)


def infer_type(op, *types):
    if op in ['+', '-', '*', '**']:
        if TabkitTypes.float in types:
            return TabkitTypes.float
        else:
            return TabkitTypes.int
    elif op == "/":
        return TabkitTypes.float
    elif op in ['==', '!=', '<', '<=', '>', '>=', '&&', '||']:
        return TabkitTypes.bool

    raise TabkitException("Unable to infer type for operation '%s'" % (op,))
