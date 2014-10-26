import ast
import sys
from itertools import chain, count

from exception import TabkitException
from header import DataDesc
from type import infer_type


def _join_exprs(exprs):
    return "".join("%s;" % expr for expr in exprs)


class MapProgram(object):
    """
    {
        row_exprs;
        if (output_cond) {
            print output;
        }
    }
    """
    def __init__(self):
        self.row_exprs = list()
        self.output_cond = list()
        self.output = list()

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

    program = MapProgram()

    try:
        output = OutputAwkGenerator(data_desc)
        for output_expr in output_exprs:
            try:
                tree = ast.parse(output_expr)
            except SyntaxError as e:
                raise TabkitException("Syntax error: %s" % e.msg)
            program.row_exprs.extend(output.visit(tree))
        program.output = output.output_code()
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

    return program, output.output_data_desc()


class GrpProgram(object):
    """
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
    """
    def __init__(self):
        self.init_aggr = list()
        self.grp_exprs = list()
        self.grp_output = list()
        self.aggr_exprs = list()
        self.aggr_output = list()

    def __str__(self):
        begin = str()
        init_aggr = _join_exprs(self.init_aggr)
        if init_aggr:
            begin = "BEGIN{%s}" % init_aggr

        body = str()
        if self.grp_exprs:
            body += _join_exprs(self.grp_exprs)

        print_expr = "print %s;" % ",".join(expr for expr in self.grp_output + self.aggr_output)
        key_expr = "&&".join(
            ["NR>1"] + ["__key_%d!=%s" % (n, expr) for n, expr in enumerate(self.grp_output)])
        body += "if(%s){%s%s}" % (key_expr, print_expr, init_aggr)

        if self.aggr_exprs:
            body += _join_exprs(self.aggr_exprs)

        if self.grp_output:
            body += _join_exprs(
                "__key_%d=%s" % (n, expr) for n, expr in enumerate(self.grp_output))

        end = str()
        if print_expr:
            end = "END(%s}" % print_expr

        return "%s{%s}%s" % (begin, body, end)


def grp_program(data_desc, grp_exprs, aggr_exprs=None):
    r'''
    >>> import re
    >>> from header import parse_header
    >>> data_desc = parse_header("# a, b, c, d")
    >>> awk, output_data_desc = grp_program(
    ...     data_desc,
    ...     grp_exprs=['a;log_b=2**int(log(b=d))'],
    ...     aggr_exprs=['sum_c=sum(c)/log_b;cnt_d=count(d)']
    ... )
    >>> print re.sub('([{};])', r'\1\n', str(awk))  # doctest: +NORMALIZE_WHITESPACE

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
            program.grp_exprs.extend(group.visit(tree))
    except TabkitException as e:
        raise TabkitException("%s in group expressions" % e)
    program.grp_output.extend(group.output_code())

    try:
        aggr = AggregateAwkGenerator(data_desc, group_context=group.context)
        for aggr_expr in aggr_exprs:
            try:
                tree = ast.parse(aggr_expr)
            except SyntaxError as e:
                raise TabkitException("Syntax error: %s" % e.msg)
            program.aggr_exprs.extend(aggr.visit(tree))
    except TabkitException as e:
        raise TabkitException("%s in aggregate expressions" % e)
    program.init_aggr.extend(aggr.init_code())
    program.aggr_output.extend(aggr.output_code())

    output_data_desc = group.output_data_desc() + aggr.output_data_desc()

    return program, output_data_desc


class Statement(object):
    def __init__(self, code):
        self.code = code


class Assignment(Statement):
    def __init__(self, code, value):
        super(Assignment, self).__init__(code)
        self.value = value


class Expression(Statement):
    def __init__(self, code, type, subexprs=None):
        super(Expression, self).__init__(code)
        self.type = type


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

    allowed_funcs = {
        'int',
        'sprintf',
        'log',
        'exp'
    }

    expression_class = Expression
    var_name_template = "__var__%d"

    def __init__(self, data_desc, context=None):
        self.data_desc = data_desc
        self.context = context or dict()
        self.var_count = count()
        super(AwkGenerator, self).__init__()

    def _new_var(self):
        return self.var_name_template % next(self.var_count)

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
        return self.expression_class(
            code="%s%s%s" % (left_expr.code, op, right_expr.code),
            type=infer_type(op, left_expr.type, right_expr.type),
            subexprs=[left_expr, right_expr])

    def visit_BoolOp(self, node):
        op = self.boolops[type(node.op)]
        exprs = [self.visit(value) for value in node.values]
        return self.expression_class(
            code="(%s)" % op.join(expr.code for expr in exprs),
            type=infer_type(op, *(expr.type for expr in exprs)),
            subexprs=exprs)

    def visit_BinOp(self, node):
        op = self.binops.get(type(node.op), None)
        if op is None:
            raise TabkitException(
                "Syntax error: binary operation '%s' is not supported" %
                (node.op.__class__.__name__,))

        left_expr = self.visit(node.left)
        right_expr = self.visit(node.right)
        return self.expression_class(
            code="(%s%s%s)" % (left_expr.code, op, right_expr.code),
            type=infer_type(op, left_expr.type, right_expr.type),
            subexprs=[left_expr, right_expr])

    def visit_Num(self, node):
        return self.expression_class(code=str(node.n), type=type(node.n))

    def visit_Str(self, node):
        return self.expression_class(code='"%s"' % node.s.replace('"', '\\"'), type=str)

    def visit_Call(self, node):
        func = node.func.id
        if node.keywords or node.kwargs or node.starargs:
            raise TabkitException("Syntax error: only positional arguments to functions allowed")
        if func not in self.allowed_funcs:
            raise TabkitException("Syntax error: unknown function '%s'" % (func,))
        args = [self.visit(arg) for arg in node.args]
        return self.expression_class(
            code="%s(%s)" % (func, ",".join(arg.code for arg in args)),
            type=infer_type(func, *(arg.type for arg in args)),
            subexprs=args)

    def visit_Name(self, node):
        if node.id in self.data_desc:
            field_index = self.data_desc.index(node.id)
            return self.expression_class(
                code="$%d" % (field_index + 1,),
                type=self.data_desc.fields[field_index].type)

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
                        self.context[field_name] = self.expression_class(
                            code="$%d" % (self.data_desc.index(field_name) + 1),
                            type=self.data_desc.get_field(field_name).type
                        )
                        self.output.append(field_name)
                    continue

            expr = self.visit(stmt)
            if not isinstance(expr, Assignment):
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
            target_var_name = self._new_var()
            if not target_name.startswith("_"):
                self.output.append(target_name)

        value = self.visit(node.value)

        assign_expr = self.expression_class(
            code=target_var_name,
            type=value.type,
            subexprs=[value])
        self.context[target_name] = assign_expr

        return Assignment(
            code="%s=%s" % (assign_expr.code, value.code),
            value=value)


class ConditionAwkGenerator(AwkGenerator):
    def visit_Module(self, node):
        code = list()
        for stmt in node.body:
            code.append(self.visit(stmt).code)
        return code


class AggregateExpression(Expression):
    def __init__(self, code, type, subexprs=None, aggregated=None):
        super(AggregateExpression, self).__init__(code, type, subexprs)
        if aggregated is None:
            if subexprs:
                aggregated = all(expr.aggregated for expr in subexprs)
            else:
                aggregated = False
        self.aggregated = aggregated


class AggregateFunction(object):
    _init_template = "%s=0"

    def __init__(self, var_name, *args):
        self.var_name = var_name
        self.args = tuple(arg.code for arg in args)

    @property
    def init(self):
        return self._init_template % self.var_name

    @property
    def code(self):
        return self._code_template % ((self.var_name,) + self.args)


class SumFunction(AggregateFunction):
    _code_template = "%s+=%s"

    def __init__(self, var_name, arg):
        super(SumFunction, self).__init__(var_name, arg)


class CountFunction(AggregateFunction):
    _code_template = "%s++"

    def __init__(self, var_name):
        super(CountFunction, self).__init__(var_name)


class AggregateAwkGenerator(OutputAwkGenerator):
    expression_class = AggregateExpression
    var_name_template = "__aggr__%d"

    aggregate_funcs = {
        'sum': SumFunction,
        'count': CountFunction
    }

    def __init__(self, data_desc, context=None, group_context=None):
        super(AggregateAwkGenerator, self).__init__(data_desc, context)
        self.group_context = group_context or dict()
        self.aggregators = list()

    def init_code(self):
        return (aggr.init for aggr in self.aggregators)

    def visit_Call(self, node):
        func = node.func.id
        if node.keywords or node.kwargs or node.starargs:
            raise TabkitException("Syntax error: only positional arguments to functions allowed")
        if func in self.aggregate_funcs:
            var_name = self._new_var()
            args = [self.visit(arg) for arg in node.args]
            self.aggregators.append(self.aggregate_funcs[func](var_name, *args))
            return self.expression_class(
                code=var_name,
                type=int,
                aggregated=True)
        return super(AggregateAwkGenerator, self).visit_Call(node)

    def visit_Num(self, node):
        expr = super(AggregateAwkGenerator, self).visit_Num(node)
        expr.aggregated = True
        return expr

    def visit_Str(self, node):
        expr = super(AggregateAwkGenerator, self).visit_Str(node)
        expr.aggregated = True
        return expr

    def visit_Name(self, node):
        if node.id in self.group_context:
            expr = self.group_context[node.id]
            return self.expression_class(
                code=expr.code,
                type=expr.type,
                aggregated=True)

        return super(AggregateAwkGenerator, self).visit_Name(node)

    def visit_Module(self, node):
        code = list()
        for stmt in node.body:
            assign = self.visit(stmt)
            if not isinstance(assign, Assignment):
                raise TabkitException('Syntax error: assign statements expected')
            if not assign.value.aggregated:
                raise TabkitException(
                    "Syntax error: need aggregate function")
            code.append(assign.code)
        return [aggr.code for aggr in self.aggregators] + code


if __name__ == "__main__":
    # import doctest
    # doctest.testmod(raise_on_error=True)
    import re
    from header import parse_header
    data_desc = parse_header("# a, b, c, d")
    awk, output_data_desc = grp_program(
        data_desc,
        grp_exprs=['a;log_b=2**int(log(b))'],
        aggr_exprs=['sum_c=sum(c)/log_b;cnt=count();_avg_d=sum(d)/count();cnt10_d=_avg_d*10']
    )
    # print re.sub('([{};])', r'\1\n', str(awk))
    print awk
    print output_data_desc
