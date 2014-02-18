from exception import TabkitException


TYPES = {
    'str': str,
    'float': float,
    'int': int,
    'bool': bool
}


def parse_type(type_str):
    type_str = type_str or 'str'
    if type_str in TYPES:
        return TYPES[type_str]
    else:
        raise TabkitException("Unknown type '%s'" % type_str)


def generic_type(*types):
    if str in types:
        return str
    if float in types:
        return float
    if int in types:
        return int
    if bool in types:
        return bool


def infer_type(op, *types):
    if op in ['+', '-', '*', '**']:
        if float in types:
            return float
        else:
            return int
    elif op == "/":
        return float
    elif op in ['==', '!=', '<', '<=', '>', '>=', '&&', '||']:
        return bool
    elif op == "int":
        return int
    elif op == "sprintf":
        return str
    elif op in ['log', 'exp']:
        return float

    raise TabkitException("Unable to infer type for operation '%s'" % (op,))
