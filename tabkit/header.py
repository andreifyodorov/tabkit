import re
from type import parse_type, generic_type
from exception import TabkitException
from collections import namedtuple

Field = namedtuple('Field', 'name type')
OrderField = namedtuple('OrderField', 'name type desc')
ORDER_TYPES = set(['str', 'num', 'generic'])

class DataDesc(object):
    def __init__(self, fields, order=None):
        self.fields = [Field(name, type) for name, type in fields]
        self.field_names = [f.name for f in self.fields]
        self.field_indices = dict((f.name, index) for index, f in enumerate(self.fields))

        if order:
            self.order = [OrderField(name, type or 'str', desc) for name, type, desc in order]
            for f in self.order:
                if not self.has_field(f.name):
                    raise TabkitException("Unknown order field '%s'" % (f.name,))
        else:
            self.order = None

    def __str__(self):
        header = "\t".join("%s:%s" % (f.name, f.type.__name__) if f.type else f.name for f in self.fields)
        if self.order:
            header += (
                "\t# ORDER: " +
                ", ".join(
                    "%s%s%s" % (
                        o.name,
                        ":" + o.type if o.type != 'str' else '',
                        ":desc" if o.desc else ''
                    )
                    for o in self.order
                )
            )
        return "# " + header

    def has_field(self, field_name):
        return self.field_indices.has_key(field_name)

    def get_field(self, field_name):
        return self.fields[self.index(field_name)]

    def index(self, field_name):
        if self.has_field(field_name):
            return self.field_indices[field_name]
        else:
            raise TabkitException("No such field '%s'" % (field_name,))

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

    >>> from sys import stdout
    >>> from exception import handle_exceptions

    >>> handle_exceptions(lambda: list(parse_order("a:desc:desc")), stderr=stdout)
    header.py: Bad order format 'a:desc:desc'
    >>> handle_exceptions(lambda: list(parse_order("a:str:str")), stderr=stdout)
    header.py: Bad order format 'a:str:str'
    >>> handle_exceptions(lambda: list(parse_order("a:desc:str")), stderr=stdout)
    header.py: Bad order format 'a:desc:str'
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
            raise TabkitException("Bad order format '%s'" % (field,))

def parse_header(header_str):
    r'''
    >>> str(parse_header('# a:int,   b:str foo # ORDER: a:num:desc b:num foo:desc'))
    '# a:int\tb:str\tfoo\t# ORDER: a:num:desc, b:num, foo:desc'

    >>> from sys import stdout
    >>> from exception import handle_exceptions

    >>> handle_exceptions(lambda: parse_header('#'), stderr=stdout)
    header.py: Bad header
    >>> handle_exceptions(lambda: parse_header('# a:int # ORDER: b'), stderr=stdout)
    header.py: Unknown order field 'b'
    '''
    if header_str[0] != "#":
        raise TabkitException("Bad header")

    header_str = header_str[1:]

    order_index = header_str.find("# ORDER:")
    if order_index >= 0:
        header_str, order_str = (header_str[:order_index - 1], header_str[order_index + len("# ORDER:"):])
        order = parse_order(order_str)
    else:
        order = None

    fields = [(name, parse_type(type)) for name, type in split_fields(header_str)]

    if len(fields) == 0:
        raise TabkitException("Bad header")

    return DataDesc(fields, order)


def generic_data_desc(desc1, desc2):
    r'''
    >>> d1 = parse_header("# a:int, b:float")
    >>> d2 = parse_header("# a:float, b")
    >>> str(generic_data_desc(d1, d2))
    '# a:float\tb'

    >>> from sys import stdout
    >>> from exception import handle_exceptions

    >>> d3 = parse_header("# a:str, b:bool, c:int")
    >>> handle_exceptions(lambda: generic_data_desc(d1, d3), stderr=stdout)
    header.py: Incompatible headers
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


if __name__ == "__main__":
    import doctest
    doctest.testmod()