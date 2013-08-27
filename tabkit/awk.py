import ast
import sys
from collections import namedtuple

from exception import TabkitException
from header import DataDesc
from type import infer_type

class AwkProgram(object):
    def __init__(self):
        self.begin = str()
        self.row_expr = str()
        self.output_cond = str()
        self.output = str()
        self.end = str()

    def __str__(self):
        begin = str()
        if self.begin:
            begin = "BEGIN{%s}" % (self.begin,)

        body = str()
        if self.row_expr:
            body = self.row_expr

        if self.output_cond:
            body += "if(%s){print %s;}" % (self.output_cond, self.output)
        else:
            body += "print %s;" % (self.output,)
            
        end = str()
        if self.end:
            end = "END{%s}" % (self.end,)
        return "%s{%s}%s" % (begin, body, end)


def map_program(data_desc, output_expr, filter_expr=None):
    r'''
    >>> from header import parse_header
    >>> data_desc = parse_header("# a, b, c, d")
    >>> awk, data_desc = map_program(data_desc, 'a=b+c;b=a/c;_hidden=a*3;new=_hidden/3;b=a+1;a;b;c;d;')
    >>> str(awk)
    '{__var__0=$2+$3;__var__1=$1/$3;__var__2=$1*3;__var__3=__var__2/3;__var__1=$1+1;print __var__0,__var__1,__var__3;}'
    >>> str(data_desc)
    '# a:int\tb:int\tnew:float'
    '''
    program = AwkProgram()

    try:
        tree = ast.parse(output_expr)
    except SyntaxError as e:
        raise TabkitException("Syntax error: %s" % (e.msg,))

    output = AwkGenerator(data_desc)
    program.row_expr = output.visit(tree)
    program.output = output.output_code()

    return program, output.output_data_desc()

Expr = namedtuple('Expr', 'code type')

class AwkGenerator(ast.NodeVisitor):
    binops = {
        ast.Add: '+',
        ast.Sub: '-',
        ast.Mult: '*',
        ast.Div: '/'
    }

    def __init__(self, data_desc):
        self.data_desc = data_desc
        self.context = dict()
        self.output = list()
        super(AwkGenerator, self).__init__()

    def output_data_desc(self):
        return DataDesc((name, self.context[name].type) for name in self.output)

    def output_code(self):
        return ",".join(self.context[name].code for name in self.output)

    def visit_Module(self, node):
        code = str()
        for stmt in node.body:
            if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Name)):
                field_name = stmt.value.id
                if self.data_desc.has_field(field_name):
                    if field_name not in self.context:
                        self.context[field_name] = Expr(
                            code = "$%d" % (self.data_desc.index(field_name) + 1,),
                            type = self.data_desc.get_field(field_name).type
                        )
                        self.output.append(field_name)
                    continue
                
            code += self.visit(stmt) + ";"

        return code

    def visit_Assign(self, node):
        if len(node.targets) != 1:
            raise TabkitException('Syntax error: multiple targets are not allowed in assignment')

        target_name = node.targets[0].id
        if target_name in self.context:
            target_var_name = self.context[target_name].code
        else:
            target_var_name = "__var__%d" % (len(self.context,))
            if not target_name.startswith("_"):
                self.output.append(target_name)

        value = self.visit(node.value)

        assign_expr = Expr(
            code = target_var_name,
            type = value.type
        )
        self.context[target_name] = assign_expr

        return "%s=%s" % (assign_expr.code, value.code)

    def visit_BinOp(self, node):
        op = self.binops.get(type(node.op), None)
        if op is None:
            raise TabkitException("Syntax error: binary operation '%s' is not supported" % (node.op.__class__.__name__,))

        left_expr = self.visit(node.left)
        right_expr = self.visit(node.right)

        return Expr(
            code = left_expr.code + op + right_expr.code,
            type = infer_type(op, left_expr.type, right_expr.type)
        )

    def visit_Num(self, node):
        return Expr(
            code = str(node.n),
            type = type(node.n)
        )

    def visit_Name(self, node):
        try:
            field_index = self.data_desc.index(node.id)
            return Expr(
                code = "$%d" % (field_index + 1,),
                type = self.data_desc.fields[field_index].type
            )
        except TabkitException:
            pass

        if self.context.has_key(node.id):
            return self.context[node.id]

        raise TabkitException("Unknown identifier '%s'" % (node.id,))


    def generic_visit(self, node):
        raise TabkitException("Syntax error: '%s' is not supported" % (node.__class__.__name__,))

if __name__ == "__main__":
    import doctest
    doctest.testmod()