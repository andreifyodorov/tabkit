import re
from collections import namedtuple

from .type import TabkitTypes, parse_type, type_name, generic_type
from .exception import TabkitException


class Field(namedtuple('Field', 'name type')):
    def __str__(self):
        if self.type == TabkitTypes.str:
            return self.name
        else:
            return "%s:%s" % (self.name, type_name(self.type))


ORDER_TYPES = {'str', 'num', 'generic'}


class OrderField(object):
    def __init__(self, name, type_=None, desc=None):
        self.name = name
        self.type = type_ or 'str'
        self.desc = desc

    def __repr__(self):
        return (
            "<%s.%s: %s, %s, %s>" %
            (__name__, self.__class__.__name__, self.name, self.type, self.desc)
        )

    def __iter__(self):
        return iter((self.name, self.type, self.desc))


def _field_list(iterable, class_):
    return [class_(*field) if not isinstance(field, class_) else field for field in iterable]


class DataDesc(object):
    def __init__(self, fields, order=None):
        self.fields = _field_list(fields, Field)
        self.field_names = [f.name for f in self.fields]
        self.field_indices = dict((f.name, index) for index, f in enumerate(self.fields))

        for index, name in enumerate(self.field_names):
            if self.index(name) != index:
                raise TabkitException("Duplicate field '%s'" % name)

        if order:
            order = _field_list(order, OrderField)
            for f in order:
                if f.name not in self:
                    raise TabkitException("Unknown order field '%s'" % f.name)
            self.order = order
        else:
            self.order = []

    def __str__(self):
        return make_header(self)

    def __len__(self):
        return len(self.fields)

    def __contains__(self, field):
        if isinstance(field, Field):
            return field.name in self.field_indices
        return field in self.field_indices

    def __iter__(self):
        return iter(self.fields)

    def __add__(self, other):
        return concat_data_desc(self, other)

    def get_field(self, field_name):
        return self.fields[self.index(field_name)]

    def index(self, field_name):
        if field_name in self:
            return self.field_indices[field_name]
        else:
            raise TabkitException("No such field '%s'" % field_name)

    def row_class(self):
        return namedtuple('DataRow', self.field_names)


def concat_data_desc(desc1, desc2):
    R'''
    >>> desc = parse_header("# a:int, b:bool # ORDER: a:num:desc, b")
    >>> str(desc + DataDesc([('x', int), ('y', str)], [('y',)]))
    '# a:int\tb:bool\tx:int\ty\t# ORDER: a:num:desc, b, y'
    '''
    return DataDesc(desc1.fields + desc2.fields, desc1.order + desc2.order)


def split_fields(string):
    for field in re.findall('[^,\s]+', string):
        if ":" in field:
            yield tuple(field.split(':', 1))
        else:
            yield (field, None)


def parse_order(string):
    '''
    >>> list(parse_order("a b"))
    [('a', None, False), ('b', None, False)]

    >>> from exception import test_exception

    >>> test_exception(lambda: parse_order("a:desc:desc"))
    doctest: Bad order format 'a:desc:desc'

    >>> test_exception(lambda: parse_order("a:str:str"))
    doctest: Bad order format 'a:str:str'

    >>> test_exception(lambda: parse_order("a:desc:str"))
    doctest: Bad order format 'a:desc:str'
    '''
    for field in re.findall('[^,\s]+', string):
        parts = field.split(':', 2)
        order_name = parts.pop(0)
        order_type = None
        order_desc = False
        try:
            for part in parts:
                if part in ORDER_TYPES:
                    if not order_desc and not order_type:
                        order_type = part
                    else:
                        raise ValueError
                elif not order_desc:
                    if part == "desc":
                        order_desc = True
                    elif part and part != "asc":
                        raise ValueError
                else:
                    raise ValueError
            yield (order_name, order_type, order_desc)
        except ValueError:
            raise TabkitException("Bad order format '%s'" % field)


def parse_header(header_str):
    R'''
    >>> str(parse_header('# a:int,   b:str foo # ORDER: a:num:desc b:num foo:desc'))
    '# a:int\tb\tfoo\t# ORDER: a:num:desc, b:num, foo:desc'

    >>> from exception import test_exception

    >>> test_exception(lambda: parse_header('#'))
    doctest: Bad header

    >>> test_exception(lambda: parse_header('# a:int # ORDER: b'))
    doctest: Unknown order field 'b'

    >>> test_exception(lambda: parse_header('# a:int, a:str'))
    doctest: Duplicate field 'a'
    '''
    if header_str[0] != "#":
        raise TabkitException("Bad header")

    header_str = header_str[1:]

    order_index = header_str.find("# ORDER:")
    if order_index >= 0:
        header_str, order_str = (
            header_str[:order_index - 1], header_str[order_index + len("# ORDER:"):])
        order = [(name, type_, desc) for name, type_, desc in parse_order(order_str)]
    else:
        order = None

    fields = [(name, parse_type(type_)) for name, type_ in split_fields(header_str)]

    if len(fields) == 0:
        raise TabkitException("Bad header")

    return DataDesc(fields, order)


def make_header(desc):
    header = "\t".join(map(str, desc))
    if desc.order:
        header += (
            "\t# ORDER: " +
            ", ".join(
                "%s%s%s" % (
                    o.name,
                    ":" + o.type if o.type != 'str' else '',
                    ":desc" if o.desc else ''
                )
                for o in desc.order
            )
        )
    return "# " + header


def generic_data_desc(desc1, desc2):
    r'''
    >>> d1 = parse_header("# a:int, b:float")
    >>> d2 = parse_header("# a:float, b")
    >>> str(generic_data_desc(d1, d2))
    '# a:float\tb'

    >>> from exception import test_exception

    >>> d3 = parse_header("# a:str, b:bool, c:int")
    >>> test_exception(lambda: generic_data_desc(d1, d3))
    doctest: Incompatible headers
    '''
    if len(desc1.fields) != len(desc2.fields):
        raise TabkitException("Incompatible headers")

    fields = []
    for f1, f2 in zip(desc1.fields, desc2.fields):
        if f1.name != f2.name:
            raise TabkitException("Incompatible headers")

        fields.append((f1.name, generic_type(f1.type, f2.type)))

    order = []

    return DataDesc(fields, order)
