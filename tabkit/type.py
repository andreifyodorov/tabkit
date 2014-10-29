from exception import TabkitException


TabkitStr = str
TabkitFloat = float
TabkitInt = int


def TabkitBoolean(x=None):
    if x == "0":
        return False
    return bool(x)


TYPES = {
    'str': TabkitStr,
    'float': TabkitFloat,
    'int': TabkitInt,
    'bool': TabkitBoolean
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


type_hierarchy = (TabkitStr, TabkitFloat, TabkitInt, TabkitBoolean)


def generic_type(*types):
    return next(t for t in type_hierarchy if t in types)


def narrowest_type(*types):
    return next(t for t in reversed(type_hierarchy) if t in types)


def infer_type(op, *types):
    if op in ['+', '-', '*', '**']:
        if TabkitFloat in types:
            return TabkitFloat
        else:
            return TabkitInt
    elif op == "/":
        return TabkitFloat
    elif op in ['==', '!=', '<', '<=', '>', '>=', '&&', '||']:
        return TabkitBoolean

    raise TabkitException("Unable to infer type for operation '%s'" % (op,))
