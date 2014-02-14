import ast
import sys
from collections import namedtuple

from exception import TabkitException
from header import DataDesc
from type import infer_type


class AwkProgram(object):
    def __init__(self):
        self.begin = str()
        self.row_exprs = list()
        self.output_cond = list()
        self.output = list()
        self.end = str()

    def __str__(self):
        begin = str()
        if self.begin:
            begin = "BEGIN{%s}" % (self.begin,)

        body = str()
        if self.row_exprs:
            body = "".join("%s;" % (expr,) for expr in self.row_exprs)

        if self.output_cond:
            body += "if(%s){print %s;}" % (
                "&&".join(self.output_cond),
                ",".join(self.output)
            )
        else:
            body += "print %s;" % (",".join(self.output),)

        end = str()
        if self.end:
            end = "END{%s}" % (self.end,)
        return "%s{%s}%s" % (begin, body, end)


def map_program(data_desc, output_exprs, filter_exprs=None):
    r'''
    >>> import re
    >>> from header import parse_header
    >>> data_desc = parse_header("# a, b, c, d")
    >>> awk, output_data_desc = map_program(
    ...     data_desc,
    ...     output_exprs=[
    ...         'a=b+c;b=a/c;_hidden=a*3;', 'new=_hidden/3', 'b=a+1', 'a', 'b', 'c', 'd'
    ...     ],
    ...     filter_exprs=['new==a*d or new==d*a', '_hidden>=new']
    ... )
    >>> print re.sub('([{};])', r'\1\n', str(awk))  # doctest: +NORMALIZE_WHITESPACE
    {
        __var__0=($2+$3);
        __var__1=($1/$3);
        __var__2=($1*3);
        __var__3=(__var__2/3);
        __var__1=($1+1);
        if((__var__3==($1*$4)||__var__3==($4*$1))&&__var__2>=__var__3){
            print __var__0,__var__1,__var__3,$3,$4;
        }
    }

    >>> str(output_data_desc)
    '# a:int\tb:int\tnew:float\tc\td'
    '''
    filter_exprs = filter_exprs or list()

    program = AwkProgram()

    try:
        output = OutputAwkGenerator(data_desc)
        for output_expr in output_exprs:
            try:
                tree = ast.parse(output_expr)
            except SyntaxError as e:
                raise TabkitException("Syntax error: %s" % (e.msg,))
            program.row_exprs.extend(output.visit(tree))
        program.output = output.output_code()
    except TabkitException as e:
        raise TabkitException("%s in output expressions" % (e,))

    try:
        cond = ConditionAwkGenerator(data_desc, output.context)
        for filter_expr in filter_exprs:
            try:
                tree = ast.parse(filter_expr)
            except SyntaxError as e:
                raise TabkitException("Syntax error: %s in filter expressions" % (e.msg,))
            program.output_cond.extend(cond.visit(tree))
    except TabkitException as e:
        raise TabkitException("%s in filter expressions" % (e,))

    return program, output.output_data_desc()


Expr = namedtuple('Expr', 'code type')


class AwkGenerator(ast.NodeVisitor):
    binops = {
        ast.Add: '+',
        ast.Sub: '-',
        ast.Mult: '*',
        ast.Pow: '**',
        ast.Div: '/'
    }

    compareops = {
        ast.Eq: '==',
        ast.NotEq: '!=',
        ast.Lt: '<',
        ast.LtE: '<=',
        ast.Gt: '>',
        ast.GtE: '>='
    }

    boolops = {
        ast.And: '&&',
        ast.Or: '||'
    }

    allowed_funcs = set("int sprintf log exp".split())

    def __init__(self, data_desc, context=None):
        self.data_desc = data_desc
        self.context = context or dict()
        super(AwkGenerator, self).__init__()

    def visit_Expr(self, node):
        return self.visit(node.value)

    def visit_Compare(self, node):
        if not (len(node.ops) == 1 and len(node.comparators) == 1):
            raise TabkitException("Syntax error: multiple comparators are not supported")

        op = self.compareops.get(type(node.ops[0]))
        if op is None:
            raise TabkitException(
                "Syntax error: compare operation '%s' is not suported" %
                (node.ops[0].__class__.__name__,)
            )

        left_expr = self.visit(node.left)
        right_expr = self.visit(node.comparators[0])
        return Expr(
            code=left_expr.code + op + right_expr.code,
            type=infer_type(op, left_expr.type, right_expr.type)
        )

    def visit_BoolOp(self, node):
        op = self.boolops[type(node.op)]
        exprs = [self.visit(value) for value in node.values]
        return Expr(
            code="(" + op.join(expr.code for expr in exprs) + ")",
            type=infer_type(op, *(expr.type for expr in exprs))
        )

    def visit_BinOp(self, node):
        op = self.binops.get(type(node.op), None)
        if op is None:
            raise TabkitException(
                "Syntax error: binary operation '%s' is not supported" %
                (node.op.__class__.__name__,)
            )

        left_expr = self.visit(node.left)
        right_expr = self.visit(node.right)
        return Expr(
            code="(" + left_expr.code + op + right_expr.code + ")",
            type=infer_type(op, left_expr.type, right_expr.type)
        )

    def visit_Num(self, node):
        return Expr(
            code=str(node.n),
            type=type(node.n)
        )

    def visit_Str(self, node):
        return Expr(
            code='"%s"' % node.s.replace('"', '\\"'),
            type=str
        )

    def visit_Call(self, node):
        func = node.func.id
        if func not in self.allowed_funcs:
            raise TabkitException("Syntax error: unknown function '%s'" % (func,))
        args = [self.visit(arg) for arg in node.args]
        return Expr(
            code="%s(%s)" % (func, ",".join(arg.code for arg in args)),
            type=infer_type(func, *(arg.type for arg in args))
        )

    def visit_Name(self, node):
        try:
            field_index = self.data_desc.index(node.id)
            return Expr(
                code="$%d" % (field_index + 1,),
                type=self.data_desc.fields[field_index].type
            )
        except TabkitException:
            pass

        if node.id in self.context:
            return self.context[node.id]

        raise TabkitException("Unknown identifier '%s'" % (node.id,))

    def generic_visit(self, node):
        raise TabkitException("Syntax error: '%s' is not supported" % (node.__class__.__name__,))


class OutputAwkGenerator(AwkGenerator):

    def __init__(self, data_desc, context=None):
        self.output = list()
        super(OutputAwkGenerator, self).__init__(data_desc, context)

    def output_code(self):
        return (self.context[name].code for name in self.output)

    def output_data_desc(self):
        return DataDesc((name, self.context[name].type) for name in self.output)

    def visit_Module(self, node):
        code = list()
        for stmt in node.body:
            # special case, no calculations, only output
            if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Name)):
                field_name = stmt.value.id
                if field_name in self.data_desc:
                    if field_name not in self.context:
                        self.context[field_name] = Expr(
                            code="$%d" % (self.data_desc.index(field_name) + 1),
                            type=self.data_desc.get_field(field_name).type
                        )
                        self.output.append(field_name)
                    continue

            expr = self.visit(stmt)
            if expr.type is not None:  # returned only by visit_Assign
                raise TabkitException('Syntax error: assign statements or field names expected')

            code.append(expr.code)

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
            code=target_var_name,
            type=value.type
        )
        self.context[target_name] = assign_expr

        return Expr(
            code="%s=%s" % (assign_expr.code, value.code),
            type=None
        )


class ConditionAwkGenerator(AwkGenerator):
    def visit_Module(self, node):
        code = list()
        for stmt in node.body:
            code.append(self.visit(stmt).code)
        return code


if __name__ == "__main__":
    import doctest
    doctest.testmod(raise_on_error=True)
