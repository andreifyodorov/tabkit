import ast
import sys
from itertools import chain, count
from collections import OrderedDict

from ..exception import TabkitException
from ..header import DataDesc
from ..type import TabkitTypes, infer_type


def _join_exprs(exprs):
    return "".join("%s;" % expr for expr in exprs)


class MapProgram(object):
    """
    Map program structure:

    {
        row_exprs;
    }
    output_cond {
        print output;
    }

    >>> str(MapProgram(output=['a', 'b']) + MapProgram(output=['c', 'd']))
    '{print a,b,c,d;}'

    """
    def __init__(self, row_exprs=None, output_cond=None, output=None):
        self.row_exprs = row_exprs or []
        self.output_cond = output_cond or []
        self.output = output or []

    def __add__(self, other):
        return MapProgram(self.row_exprs + other.row_exprs,
                          self.output_cond + other.output_cond,
                          self.output + other.output)

    def __str__(self):
        row_exprs = _join_exprs(self.row_exprs)
        if row_exprs:
            row_exprs = "{%s}" % row_exprs
        output_cond = "&&".join(self.output_cond)
        output_exprs = ",".join(self.output)
        if output_exprs:
            output_exprs = "{print %s;}" % output_exprs
        return "%s%s%s" % (row_exprs, output_cond, output_exprs)


def map_program(data_desc, output_exprs, filter_exprs=None):
    r'''
    >>> import re
    >>> from ..header import parse_header
    >>> data_desc = parse_header("# a, b, c, d")
    >>> awk, output_data_desc = map_program(
    ...     data_desc,
    ...     output_exprs=[
    ...         'a=b+c;b=a/c;_hidden=a*3;', 'new=_hidden/3', 'b=a+1', 'a2=a', 'a', 'b', 'c', 'd'
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
        __var__0=$1;
        __var__1=$2;
    }
    (__var__3==($1*$4)||__var__3==($4*$1))&&__var__2>=__var__3{
        print __var__0,__var__1,__var__3,$1,$3,$4;
    }

    >>> str(output_data_desc)
    '# a\tb\tnew:float\ta2\tc\td'
    '''
    filter_exprs = filter_exprs or list()

    program = MapProgram()

    try:
        output = OutputAwkGenerator(data_desc)
        for output_expr in output_exprs:
            try:
                tree = ast.parse(output_expr)
            except SyntaxError as e:
                raise TabkitException("Syntax error: %s" % e.msg)
            program.row_exprs.extend(output.visit(tree))
        program.output.extend(output.output_code())
    except TabkitException as e:
        raise TabkitException("%s in output expressions" % e)

    try:
        cond = ConditionAwkGenerator(data_desc, output.context)
        for filter_expr in filter_exprs:
            try:
                tree = ast.parse(filter_expr)
            except SyntaxError as e:
                raise TabkitException("Syntax error: %s in filter expressions" % e.msg)
            program.output_cond.extend(cond.visit(tree))
    except TabkitException as e:
        raise TabkitException("%s in filter expressions" % e)

    return program, output.output_data_desc() if output_exprs else data_desc


class Statement(object):
    def __init__(self, code, children=None):
        self.code = code
        self.children = children


class Assignment(Statement):
    def __init__(self, code, value, children=None):
        super(Assignment, self).__init__(code, children)
        self.value = value


class OmittedAssignment(Assignment):
    def __init__(self, value, children=None):
        super(OmittedAssignment, self).__init__(None, value, children)


class Expression(Statement):
    def __init__(self, code, type, children=None):
        super(Expression, self).__init__(code, children)
        self.type = type
        self.children = children


class SimpleExpression(Expression):
    """ Simple column expression like '$1' """
    pass


class Function(object):
    def __init__(self, template, type):
        self.template = template
        self.type = type

    def code(self, args):
        return self.template % ",".join(arg.code for arg in args)


class AwkNodeVisitor(ast.NodeVisitor):
    compareops = {
        ast.Eq: '==',
        ast.NotEq: '!=',
        ast.Lt: '<',
        ast.LtE: '<=',
        ast.Gt: '>',
        ast.GtE: '>='
    }

    def visit_Compare(self, node):
        if not (len(node.ops) == 1 and len(node.comparators) == 1):
            raise TabkitException("Syntax error: multiple comparators are not supported")
        op = type(node.ops[0])
        if op not in self.compareops:
            raise TabkitException(
                "Syntax error: compare operation '%s' is not suported" % op.__name__)
        return [self.visit(node.left), self.visit(node.comparators[0])]

    boolops = {
        ast.And: '&&',
        ast.Or: '||'
    }

    def visit_BoolOp(self, node):
        op = type(node.op)
        if op not in self.boolops:
            raise TabkitException(
                "Syntax error: boolean operation '%s' is not supported" % op.__name__)
        return [self.visit(value) for value in node.values]

    binops = {
        ast.Add: '+',
        ast.Sub: '-',
        ast.Mult: '*',
        ast.Pow: '**',
        ast.Div: '/'
    }

    def visit_BinOp(self, node):
        op = type(node.op)
        if op not in self.binops:
            raise TabkitException(
                "Syntax error: binary operation '%s' is not supported" % op.__name__)
        return [self.visit(node.left), self.visit(node.right)]

    funcs = {
        'int': Function('int(%s)', TabkitTypes.int),
        'sprintf': Function('sprintf(%s)', TabkitTypes.str),
        'log': Function('log(%s)', TabkitTypes.float),
        'exp': Function('exp(%s)', TabkitTypes.float),
        'bool': Function('!!%s', TabkitTypes.bool)
    }

    def visit_Call(self, node):
        if node.keywords or node.kwargs or node.starargs:
            raise TabkitException("Syntax error: only positional arguments to functions allowed")
        if node.func.id in self.funcs:
            return self.visit_Function(node)
        raise TabkitException("Syntax error: unknown function '%s'" % node.func.id)

    def visit_Function(self, node):
        return [self.visit(arg) for arg in node.args]

    def visit_Expr(self, node):
        return self.visit(node.value)

    def visit_Num(self, node):
        pass

    def visit_Str(self, node):
        pass

    def visit_Name(self, node):
        pass

    def generic_visit(self, node):
        raise TabkitException("Syntax error: '%s' is not supported" % type(node).__name__)


class AwkGenerator(AwkNodeVisitor):
    def __init__(self, data_desc, context=None):
        self.data_desc = data_desc
        self.context = context or OrderedDict()
        self.var_count = count()
        super(AwkGenerator, self).__init__()

    var_name_template = "__var__%x"

    def _new_var(self):
        return self.var_name_template % next(self.var_count)

    def visit_Compare(self, node):
        left_expr, right_expr = super(AwkGenerator, self).visit_Compare(node)
        op = self.compareops.get(type(node.ops[0]))
        return Expression(
            code="%s%s%s" % (left_expr.code, op, right_expr.code),
            type=infer_type(op, left_expr.type, right_expr.type),
            children=[left_expr, right_expr]
        )

    def visit_BoolOp(self, node):
        exprs = super(AwkGenerator, self).visit_BoolOp(node)
        op = self.boolops[type(node.op)]
        return Expression(
            code="(%s)" % op.join(expr.code for expr in exprs),
            type=infer_type(op, *(expr.type for expr in exprs)),
            children=exprs
        )

    def visit_BinOp(self, node):
        left_expr, right_expr = super(AwkGenerator, self).visit_BinOp(node)
        op = self.binops[type(node.op)]
        return Expression(
            code="(%s%s%s)" % (left_expr.code, op, right_expr.code),
            type=infer_type(op, left_expr.type, right_expr.type),
            children=[left_expr, right_expr]
        )

    def visit_Num(self, node):
        return Expression(
            code=str(node.n),
            type=type(node.n)
        )

    def visit_Str(self, node):
        return Expression(
            code='"%s"' % node.s.replace('"', '\\"'),
            type=str
        )

    def visit_Function(self, node):
        func = self.funcs[node.func.id]
        args = super(AwkGenerator, self).visit_Function(node)
        return Expression(
            code=func.code(args),
            type=func.type,
            children=args
        )

    def visit_Name(self, node):
        if node.id in self.data_desc:
            field_index = self.data_desc.index(node.id)
            return SimpleExpression(
                code="$%d" % (field_index + 1),
                type=self.data_desc.fields[field_index].type)

        if node.id in self.context:
            return self.context[node.id]

        raise TabkitException("Unknown identifier '%s'" % (node.id,))


class OutputAwkGenerator(AwkGenerator):
    def __init__(self, data_desc, context=None):
        self.output = set()
        super(OutputAwkGenerator, self).__init__(data_desc, context)

    def output_context(self):
        return ((name, expr) for name, expr in self.context.iteritems() if name in self.output)

    def output_code(self):
        return (expr.code for name, expr in self.output_context())

    def output_data_desc(self):
        return DataDesc((name, expr.type) for name, expr in self.output_context())

    def visit_Assign(self, node):
        if len(node.targets) != 1:
            raise TabkitException('Syntax error: multiple targets are not allowed in assignment')

        target_name = node.targets[0].id
        value = self.visit(node.value)

        if target_name in self.context:
            target_var_name = self.context[target_name].code
        else:
            if not target_name.startswith("_"):
                self.output.add(target_name)
            if isinstance(value, SimpleExpression):
                self.context[target_name] = value
                return OmittedAssignment(value)
            target_var_name = self._new_var()

        assign_expr = Expression(
            code=target_var_name,
            type=value.type,
            children=[value])
        self.context[target_name] = assign_expr

        return Assignment(
            code="%s=%s" % (assign_expr.code, value.code),
            value=value)

    def visit_Module(self, node):
        code = list()
        for stmt in node.body:
            # syntactic sugar, no assignment, just mention var name
            if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Name)):
                stmt = ast.Assign(targets=[stmt.value], value=stmt.value)

            assign = self.visit(stmt)
            if not isinstance(assign, Assignment):
                raise TabkitException('Syntax error: assign statements or field names expected')
            if not isinstance(assign, OmittedAssignment):
                code.append(assign.code)
        return code


class ConditionAwkGenerator(AwkGenerator):
    def visit_Module(self, node):
        code = list()
        for stmt in node.body:
            code.append(self.visit(stmt).code)
        return code
