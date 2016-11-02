import ast
import sys
from itertools import chain
from collections import OrderedDict

from .map import (
    _join_exprs, Statement, Assignment, OmittedAssignment, Expression, SimpleExpression,
    AwkNodeVisitor, OutputAwkGenerator
)
from ..exception import TabkitException
from ..type import TabkitTypes


class GrpProgram(object):
    """
    Group program structure:

    {
        grp_exrps;
    }
    (_keys != grp_output) {
        if (NR>1) print _keys, aggr_output;
        _keys = grp_output;
        init_aggr;
    }
    {
        aggr_exprs;
    }
    END {
        if (NR>0) print grp_ouput, aggr_output;
    }

    >>> str(GrpProgram(grp_keys=['a'], grp_output=['a']) + GrpProgram(aggr_output=['c', 'd']))
    'NR==1||__key__0!=a{if(NR>1)print __key__0,c,d;__key__0=a;}END{if(NR>0)print __key__0,c,d;}'

    """
    def __init__(self, init_aggr=None, grp_keys=None, grp_exprs=None, grp_output=None,
                 aggr_exprs=None, aggr_output=None):
        self.init_aggr = init_aggr or []
        self.grp_keys = grp_keys or []
        self.grp_exprs = grp_exprs or []
        self.grp_output = grp_output or []
        self.aggr_exprs = aggr_exprs or []
        self.aggr_output = aggr_output or []

    def __add__(self, other):
        return GrpProgram(self.init_aggr + other.init_aggr,
                          self.grp_keys + other.grp_keys,
                          self.grp_exprs + other.grp_exprs,
                          self.grp_output + other.grp_output,
                          self.aggr_exprs + other.aggr_exprs,
                          self.aggr_output + other.aggr_output)

    def __str__(self):
        grp_exprs = _join_exprs(self.grp_exprs)
        if grp_exprs:
            grp_exprs = "{%s}" % grp_exprs

        keys = OrderedDict((expr, "__key__%x" % n) for n, expr in enumerate(self.grp_keys))
        print_exprs = [keys[expr] for expr in self.grp_output] + self.aggr_output
        print_expr = "print %s;" % ",".join(expr for expr in print_exprs)
        key_cond = "%s" % "||".join("%s!=%s" % (var, expr) for expr, var in keys.iteritems())
        key_exprs = _join_exprs("%s=%s" % (var, expr) for expr, var in keys.iteritems())

        init_aggr = _join_exprs(self.init_aggr)
        aggr_exprs = _join_exprs(self.aggr_exprs)
        if aggr_exprs:
            aggr_exprs = "{%s}" % aggr_exprs

        return "%sNR==1||%s{if(NR>1)%s%s%s}%sEND{if(NR>0)%s}" % (
            grp_exprs, key_cond, print_expr, key_exprs, init_aggr, aggr_exprs, print_expr)


def grp_program(data_desc, grp_exprs, aggr_exprs=None):
    R'''
    >>> import re
    >>> from ..header import parse_header
    >>> data_desc = parse_header("# a, b, c, d")
    >>> awk, output_data_desc = grp_program(
    ...     data_desc,
    ...     grp_exprs=['new_a=a;b;log_b=2**int(log(b))'],
    ...     aggr_exprs=['sum_c=sum(c)/log_b', 'cnt_d=count()']
    ... )
    >>> print re.sub('([{};])', r'\1\n', str(awk))  # doctest: +NORMALIZE_WHITESPACE
    {
        __var__0=(2**int(log($2)));
    }
    NR==1||__key__0!=$1||__key__1!=$2||__key__2!=__var__0{
        if(NR>1)print __key__0,__key__1,__key__2,__aggr__1,__aggr__2;
        __key__0=$1;
        __key__1=$2;
        __key__2=__var__0;
        __aggr__0=0;
        __aggr__2=0;
    }
    {
        __aggr__0+=$3;
        __aggr__1=(__aggr__0/__var__0);
        __aggr__2++;
    }
    END{
        if(NR>0)print __key__0,__key__1,__key__2,__aggr__1,__aggr__2;
    }
    >>> str(output_data_desc)
    '# new_a\tb\tlog_b:int\tsum_c:float\tcnt_d:int'
    '''
    aggr_exprs = aggr_exprs or list()

    program = GrpProgram()

    try:
        group = GroupKeysAwkGenerator(data_desc)
        for grp_expr in grp_exprs:
            try:
                tree = ast.parse(grp_expr)
            except SyntaxError as e:
                raise TabkitException("Syntax error: %s" % e.msg)
            program.grp_exprs.extend(group.visit(tree))
    except TabkitException as e:
        raise TabkitException("%s in group expressions" % e)
    program.grp_keys.extend(group.group_keys())
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


class GroupKeysAwkGenerator(OutputAwkGenerator):
    def group_keys(self):
        return (expr.code for name, expr in self.context.iteritems())


class AggregateExpression(Expression):
    def __init__(self, code, type, children=None, aggregators=None):
        combined_aggregators = []
        if children:
            combined_aggregators.append(
                chain.from_iterable(
                    child.aggregators for child in children
                    if isinstance(child, AggregateExpression))
            )
        if aggregators:
            combined_aggregators.append(aggregators)
        self.aggregators = chain.from_iterable(combined_aggregators)
        super(AggregateExpression, self).__init__(code, type, children)

    @classmethod
    def from_expression(cls, expr):
        return cls(code=expr.code, type=expr.type, children=expr.children)


class SimpleAggregateExpressions(AggregateExpression, SimpleExpression):
    pass


class AggregateFunction(object):
    init_code_template = None
    code_template = None

    def _set_code_attr(self, attr, *args, **kwargs):
        template = getattr(self, "%s_template" % attr)
        setattr(self, attr, template.format(*args, **kwargs) if template else None)

    def __init__(self, var_name, *args, **kwargs):
        self._set_code_attr('init_code', var_name=var_name, **kwargs)
        self._set_code_attr('code', *(arg.code for arg in args), var_name=var_name, **kwargs)


class CumulativeSumFunction(AggregateFunction):
    code_template = "{var_name}+={0}"

    def __init__(self, var_name, arg):
        super(CumulativeSumFunction, self).__init__(var_name, arg)
        self.type = arg.type


class SumFunction(CumulativeSumFunction):
    init_code_template = "{var_name}=0"


class CumulativeCountFunction(AggregateFunction):
    code_template = "{var_name}++"

    def __init__(self, var_name):
        super(CumulativeCountFunction, self).__init__(var_name)
        self.type = TabkitTypes.int


class CountFunction(CumulativeCountFunction):
    init_code_template = "{var_name}=0"


class GroupConcatFunction(AggregateFunction):
    init_code_template = '{var_name}=""'
    code_template = '{var_name}={var_name} ({var_name}?{delimeter}:"") {0}'

    def __init__(self, var_name, arg, delimeter=None):
        if delimeter:
            if delimeter.type != TabkitTypes.str:
                raise TabkitException("Syntax error: group_concat delimiter should be string")
            delimeter = delimeter.code
        else:
            delimeter = '", "'
        super(GroupConcatFunction, self).__init__(var_name, arg, delimeter=delimeter)
        self.type = TabkitTypes.str


class AggregateAwkNodeVisitor(AwkNodeVisitor):
    aggregate_funcs = {
        'cumsum': CumulativeSumFunction,
        'sum': SumFunction,
        'cumcount': CumulativeCountFunction,
        'count': CountFunction,
        'group_concat': GroupConcatFunction
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
        return (aggr.init_code for aggr in self.aggregators if aggr.init_code)

    def visit(self, node):
        """ If all constituent expression are aggregated, then the result is aggregated """
        expr = super(AggregateAwkGenerator, self).visit(node)
        if (isinstance(expr, Statement)
                and not isinstance(expr, AggregateExpression)
                and expr.children
                and all(isinstance(child, AggregateExpression) for child in expr.children)):
            return AggregateExpression.from_expression(expr)
        return expr

    def visit_AggregateFunction(self, node):
        var_name = self._new_var()
        args = super(AggregateAwkGenerator, self).visit_AggregateFunction(node)
        func = self.aggregate_funcs[node.func.id](var_name, *args)
        return SimpleAggregateExpressions(
            code=var_name,
            type=func.type,
            children=args,
            aggregators=[func]
        )

    def visit_Num(self, node):
        return AggregateExpression.from_expression(
            super(AggregateAwkGenerator, self).visit_Num(node))

    def visit_Str(self, node):
        return AggregateExpression.from_expression(
            super(AggregateAwkGenerator, self).visit_Str(node))

    def visit_Name(self, node):
        if node.id in self.group_context:
            expr = self.group_context[node.id]
            return AggregateExpression(
                code=expr.code,
                type=expr.type
            )
        return super(AggregateAwkGenerator, self).visit_Name(node)

    def visit_Module(self, node):
        code = list()
        for stmt in node.body:
            assign = self.visit(stmt)
            if not isinstance(assign, Assignment):
                raise TabkitException('Syntax error: assign statements expected')
            if not isinstance(assign.value, AggregateExpression):
                raise TabkitException('Syntax error: need aggregate function')
            for aggr in assign.value.aggregators:
                self.aggregators.append(aggr)
                code.append(aggr.code)
            if not isinstance(assign, OmittedAssignment):
                code.append(assign.code)
        return code
