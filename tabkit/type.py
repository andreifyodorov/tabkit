from exception import TabkitException


def Boolean(x=None):
    if x == "0":
        return False
    return bool(x)


TYPES = {
    'str': str,
    'float': float,
    'int': int,
    'bool': Boolean
}


TYPE_NAMES = {type_: name for name, type_ in TYPES.iteritems()}


def parse_type(type_str):
    type_str = type_str or 'str'
    type_ = TYPES.get(type_str)
    if not type_:
        raise TabkitException("Unknown type '%s'" % type_str)
    return type_


def type_name(type_):
    name = TYPE_NAMES.get(type_)
    if not name:
        raise TabkitException("Uknown object '%r' passed as type" % type_)
    return name


type_hierarchy = (str, float, int, Boolean)


def generic_type(*types):
    return next(t for t in type_hierarchy if t in types)


def narrowest_type(*types):
    return next(t for t in reversed(type_hierarchy) if t in types)


def infer_type(op, *types):
    if op in ['+', '-', '*', '**']:
        if float in types:
            return float
        else:
            return int
    elif op == "/":
        return float
    elif op in ['==', '!=', '<', '<=', '>', '>=', '&&', '||']:
        return Boolean
    elif op == "int":
        return int
    elif op == "sprintf":
        return str
    elif op in ['log', 'exp']:
        return float

    raise TabkitException("Unable to infer type for operation '%s'" % (op,))
