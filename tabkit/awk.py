import ast
import sys
from itertools import chain, count

from exception import TabkitException
from header import DataDesc
from type import TabkitTypes, infer_type


class List(list):
    def __call__(self, iterable):
        self.extend(iterable)


def _join_exprs(exprs):
    return "".join("%s;" % expr for expr in exprs)


class MapProgram(object):
    """
    Map program structure:

    {
        row_exprs;
        if (output_cond) {
            print output;
        }
    }

    >>> str(MapProgram(output=['a', 'b']) + MapProgram(output=['c', 'd']))
    '{print a,b,c,d;}'

    """
    def __init__(self, row_exprs=None, output_cond=None, output=None):
        self.row_exprs = List(row_exprs or [])
        self.output_cond = List(output_cond or [])
        self.output = List(output or [])

    def __add__(self, other):
        return MapProgram(self.row_exprs + other.row_exprs,
                          self.output_cond + other.output_cond,
                          self.output + other.output)

    def __str__(self):
        body = str()
        if self.row_exprs:
            body += _join_exprs(self.row_exprs)
        print_expr = "print %s;" % ",".join(self.output)
        if self.output_cond:
            body += "if(%s){%s}" % ("&&".join(self.output_cond), print_expr)
        else:
            body += print_expr
        return "{%s}" % body


def map_program(data_desc, output_exprs, filter_exprs=None):
    r'''
    >>> import re
    >>> from header import parse_header
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
        if((__var__3==($1*$4)||__var__3==($4*$1))&&__var__2>=__var__3){
            print __var__0,__var__1,__var__3,$1,$3,$4;
        }
    }

    >>> str(output_data_desc)
    '# a:int\tb:int\tnew:float\ta2\tc\td'
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
            program.row_exprs(output.visit(tree))
        program.output(output.output_code())
    except TabkitException as e:
        raise TabkitException("%s in output expressions" % e)

    try:
        cond = ConditionAwkGenerator(data_desc, output.context)
        for filter_expr in filter_exprs:
            try:
                tree = ast.parse(filter_expr)
            except SyntaxError as e:
                raise TabkitException("Syntax error: %s in filter expressions" % e.msg)
            program.output_cond(cond.visit(tree))
    except TabkitException as e:
        raise TabkitException("%s in filter expressions" % e)

    return program, output.output_data_desc()


class GrpProgram(object):
    """
    Group program structure:

    BEGIN {
        init_aggr;
    }
    {
        grp_exrps;
        if (NR>1 && _keys != grp_output) {
            print grp_output, aggr_output;
            init_aggr;
        }
        aggr_exprs;
        _keys = grp_output;
    }
    END {
        print grp_ouput, aggr_output;
    }

    >>> str(GrpProgram(grp_output=['a', 'b']) + GrpProgram(aggr_output=['c', 'd']))
    '{if(NR>1&&__key__0!=a&&__key__1!=b){print a,b,c,d;}__key__0=a;__key__1=b;}END{print a,b,c,d;}'

    """
    def __init__(self, init_aggr=None, grp_exprs=None, grp_output=None,
                 aggr_exprs=None, aggr_output=None):
        self.init_aggr = List(init_aggr or [])
        self.grp_exprs = List(grp_exprs or [])
        self.grp_output = List(grp_output or [])
        self.aggr_exprs = List(aggr_exprs or [])
        self.aggr_output = List(aggr_output or [])

    def __add__(self, other):
        return GrpProgram(self.init_aggr + other.init_aggr,
                          self.grp_exprs + other.grp_exprs,
                          self.grp_output + other.grp_output,
                          self.aggr_exprs + other.aggr_exprs,
                          self.aggr_output + other.aggr_output)

    def __str__(self):
        begin = str()
        init_aggr = _join_exprs(self.init_aggr)
        if init_aggr:
            begin = "BEGIN{%s}" % init_aggr

        body = str()
        if self.grp_exprs:
            body += _join_exprs(self.grp_exprs)

        keys = [("__key__%x" % n, expr) for n, expr in enumerate(self.grp_output)]
        print_expr = "print %s;" % ",".join(expr for expr in self.grp_output + self.aggr_output)
        key_expr = "&&".join(
            ["NR>1"] + ["%s!=%s" % (var, expr) for var, expr in keys])
        body += "if(%s){%s%s}" % (key_expr, print_expr, init_aggr)

        if self.aggr_exprs:
            body += _join_exprs(self.aggr_exprs)

        if self.grp_output:
            body += _join_exprs("%s=%s" % (var, expr) for var, expr in keys)

        end = str()
        if print_expr:
            end = "END{%s}" % print_expr

        return "%s{%s}%s" % (begin, body, end)


def grp_program(data_desc, grp_exprs, aggr_exprs=None):
    R'''
    >>> import re
    >>> from header import parse_header
    >>> data_desc = parse_header("# a, b, c, d")
    >>> awk, output_data_desc = grp_program(
    ...     data_desc,
    ...     grp_exprs=['new_a=a;b;log_b=2**int(log(b))'],
    ...     aggr_exprs=['sum_c=sum(c)/log_b;cnt_d=count()']
    ... )
    >>> print re.sub('([{};])', r'\1\n', str(awk))  # doctest: +NORMALIZE_WHITESPACE
    BEGIN{
        __aggr__0=0;
        __aggr__2=0;
    }
    {
        __var__0=(2**int(log($2)));
        if(NR>1&&__key__0!=$1&&__key__1!=$2&&__key__2!=__var__0){
            print $1,$2,__var__0,__aggr__1,__aggr__2;
            __aggr__0=0;
            __aggr__2=0;
        }
        __aggr__0+=$3;
        __aggr__2++;
        __aggr__1=(__aggr__0/__var__0);
        __key__0=$1;
        __key__1=$2;
        __key__2=__var__0;
    }
    END{
        print $1,$2,__var__0,__aggr__1,__aggr__2;
    }
    >>> str(output_data_desc)
    '# new_a\tb\tlog_b:int\tsum_c:float\tcnt_d:int'
    '''
    aggr_exprs = aggr_exprs or list()

    program = GrpProgram()

    try:
        group = OutputAwkGenerator(data_desc)
        for grp_expr in grp_exprs:
            try:
                tree = ast.parse(grp_expr)
            except SyntaxError as e:
                raise TabkitException("Syntax error: %s" % e.msg)
            program.grp_exprs(group.visit(tree))
    except TabkitException as e:
        raise TabkitException("%s in group expressions" % e)
    program.grp_output(group.output_code())

    try:
        aggr = AggregateAwkGenerator(data_desc, group_context=group.context)
        for aggr_expr in aggr_exprs:
            try:
                tree = ast.parse(aggr_expr)
            except SyntaxError as e:
                raise TabkitException("Syntax error: %s" % e.msg)
            program.aggr_exprs(aggr.visit(tree))
    except TabkitException as e:
        raise TabkitException("%s in aggregate expressions" % e)
    program.init_aggr(aggr.init_code())
    program.aggr_output(aggr.output_code())

    output_data_desc = group.output_data_desc() + aggr.output_data_desc()

    return program, output_data_desc


class Statement(object):
    def __init__(self, code, children=None):
        self.code = code
        self.children = children


class Assignment(Statement):
    def __init__(self, code, value, children=None):
        super(Assignment, self).__init__(code, children)
        self.value = value


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
        self.context = context or dict()
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
                code="$%d" % (field_index + 1,),
                type=self.data_desc.fields[field_index].type)

        if node.id in self.context:
            return self.context[node.id]

        raise TabkitException("Unknown identifier '%s'" % (node.id,))


class OutputAwkGenerator(AwkGenerator):

    def __init__(self, data_desc, context=None):
        self.output = list()
        super(OutputAwkGenerator, self).__init__(data_desc, context)

    def output_code(self):
        return (self.context[name].code for name in self.output)

    def output_data_desc(self):
        return DataDesc((name, self.context[name].type) for name in self.output)

    def visit_Assign(self, node):
        if len(node.targets) != 1:
            raise TabkitException('Syntax error: multiple targets are not allowed in assignment')

        target_name = node.targets[0].id
        value = self.visit(node.value)

        if target_name in self.context:
            target_var_name = self.context[target_name].code
        else:
            if not target_name.startswith("_"):
                self.output.append(target_name)
            if isinstance(value, SimpleExpression):
                self.context[target_name] = value
                return None
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
            # special case, no calculations, only output
            if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Name)):
                field_name = stmt.value.id
                if field_name in self.data_desc:
                    if field_name not in self.context:
                        self.context[field_name] = Expression(
                            code="$%d" % (self.data_desc.index(field_name) + 1),
                            type=self.data_desc.get_field(field_name).type
                        )
                        self.output.append(field_name)
                    continue

            assign = self.visit(stmt)
            if assign is None:
                continue
            if not isinstance(assign, Assignment):
                raise TabkitException('Syntax error: assign statements or field names expected')
            code.append(assign.code)
        return code


class ConditionAwkGenerator(AwkGenerator):
    def visit_Module(self, node):
        code = list()
        for stmt in node.body:
            code.append(self.visit(stmt).code)
        return code


class AggregatedExpression(Expression):
    @classmethod
    def from_expression(cls, expr):
        return cls(code=expr.code, type=expr.type, children=expr.children)


class SimpleAggregatedExpressions(AggregatedExpression, SimpleExpression):
    pass


class AggregateFunction(object):
    init_code_template = "%s=0"

    def __init__(self, var_name, *args):
        self.var_name = var_name
        self.args = tuple(arg.code for arg in args)

    @property
    def init_code(self):
        return self.init_code_template % self.var_name

    @property
    def code(self):
        return self.code_template % ((self.var_name,) + self.args)


class SumFunction(AggregateFunction):
    code_template = "%s+=%s"

    def __init__(self, var_name, arg):
        super(SumFunction, self).__init__(var_name, arg)
        self.type = arg.type


class CountFunction(AggregateFunction):
    code_template = "%s++"

    def __init__(self, var_name):
        super(CountFunction, self).__init__(var_name)
        self.type = TabkitTypes.int


class AggregateAwkNodeVisitor(AwkNodeVisitor):
    aggregate_funcs = {
        'sum': SumFunction,
        'count': CountFunction
    }

    def visit_Call(self, node):
        if node.keywords or node.kwargs or node.starargs:
            raise TabkitException("Syntax error: only positional arguments to functions allowed")
        if node.func.id in self.funcs:
            return self.visit_Function(node)
        if node.func.id in self.aggregate_funcs:
            return self.visit_AggregateFunction(node)
        raise TabkitException("Syntax error: unknown function '%s'" % node.func.id)

    def visit_AggregateFunction(self, node):
        return [self.visit(arg) for arg in node.args]


class AggregateAwkGenerator(AggregateAwkNodeVisitor, OutputAwkGenerator):
    var_name_template = "__aggr__%x"

    def __init__(self, data_desc, context=None, group_context=None):
        super(AggregateAwkGenerator, self).__init__(data_desc, context)
        self.group_context = group_context or dict()
        self.aggregators = list()

    def init_code(self):
        return (aggr.init_code for aggr in self.aggregators)

    def visit(self, node):
        """ If all constituent expression are aggregated, then the result is aggregated """
        expr = super(AggregateAwkGenerator, self).visit(node)
        if (isinstance(expr, Statement)
                and not isinstance(expr, AggregatedExpression)
                and expr.children
                and all(isinstance(child, AggregatedExpression) for child in expr.children)):
            return AggregatedExpression.from_expression(expr)
        return expr

    def visit_AggregateFunction(self, node):
        var_name = self._new_var()
        args = super(AggregateAwkGenerator, self).visit_AggregateFunction(node)
        func = self.aggregate_funcs[node.func.id](var_name, *args)
        self.aggregators.append(func)
        return SimpleAggregatedExpressions(
            code=var_name,
            type=func.type,
            children=args
        )

    def visit_Num(self, node):
        return AggregatedExpression.from_expression(
            super(AggregateAwkGenerator, self).visit_Num(node))

    def visit_Str(self, node):
        return AggregatedExpression.from_expression(
            super(AggregateAwkGenerator, self).visit_Str(node))

    def visit_Name(self, node):
        if node.id in self.group_context:
            expr = self.group_context[node.id]
            return AggregatedExpression(
                code=expr.code,
                type=expr.type
            )
        return super(AggregateAwkGenerator, self).visit_Name(node)

    def visit_Module(self, node):
        code = list()
        for stmt in node.body:
            assign = self.visit(stmt)
            if assign is None:
                continue
            if not isinstance(assign, Assignment):
                raise TabkitException('Syntax error: assign statements expected')
            if not isinstance(assign.value, AggregatedExpression):
                raise TabkitException(
                    "Syntax error: need aggregate function")
            code.append(assign.code)
        return [aggr.code for aggr in self.aggregators] + code


if __name__ == "__main__":
    import doctest
    doctest.testmod(raise_on_error=True)
