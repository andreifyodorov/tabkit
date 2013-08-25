import re
from type import parse_type, generic_type
from exception import TabkitException

class DataDesc(object):
    def __init__(self, fields, order=None):
        self.fields = fields
        self.field_names = [name for name, type in fields]
        self.order = order

    def __str__(self):
        header = "\t".join("%s:%s" % (name, type.__name__) if type else name for name, type in self.fields)
        if self.order:
            header += "\t# ORDER: " + ", ".join("%s:desc" % (name,) if desc else name for name, desc in self.order)
        return "# " + header

    def index(self, field_name):
        try:
            return self.field_names.index(field_name)
        except ValueError:
            raise TabkitException("No such field '%s'" % (field_name,))

def split_fields(string):
    for field in re.findall('[^,\s]+', string):
        if ":" in field:
            yield tuple(field.split(':', 1))
        else:
            yield (field, None)

def parse_header(header_str):
    r'''
    >>> str(parse_header('# a:int,   b:str foo # ORDER: a:desc b c'))
    '# a:int\tb:str\tfoo # ORDER: a:desc, b, c'
    >>> try:
    ...     parse_header('#')
    ... except Exception as e:
    ...     print e
    Bad header: '#'
    '''
    if header_str[0] != "#":
        raise TabkitException("Bad header")

    header_str = header_str[1:]

    order_index = header_str.find("# ORDER:")
    if order_index >= 0:
        header_str, order_str = (header_str[:order_index - 1], header_str[order_index + len("# ORDER:"):])
        order = [(name, bool(desc)) for name, desc in split_fields(order_str)]
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
    >>> d3 = parse_header("# a:str, b:bool, c:int")
    >>> try:
    ...     str(generic_data_desc(d1, d3))
    ... except Exception as e:
    ...     print e
    Incompatible headers: '# a:int, b:float' and '# a:str, b:bool, c:int'
    '''
    if len(desc1.fields) != len(desc2.fields):
        raise TabkitException("Incompatable headers")

    fields = []
    for (name1, type1), (name2, type2) in zip(desc1.fields, desc2.fields):
        if name1 != name2:
            raise TabkitException("Incompatable headers")

        fields.append((name1, generic_type(type1, type2)))

    order = []
        
    return DataDesc(fields, order)


if __name__ == "__main__":
    import doctest
    doctest.testmod()