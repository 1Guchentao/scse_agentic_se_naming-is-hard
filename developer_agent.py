"""Generate and check a narrowly defined next-action Python function."""

import ast
from itertools import product

from local_qwen import ask
from planner_agent import MOVES, validate_plan


INSTRUCTIONS = """Implement the supplied JSON plan as one Python function:
navigate(obstacles, target=None). Return raw Python source only.
obstacles has keys "FORWARD", "LEFT", "RIGHT"; True means BLOCKED, False means
CLEAR. target is None or one of these strings. A target can still be BLOCKED.
The first decision MUST check BOTH that target is provided AND that
not obstacles[target] before returning target. Never return a blocked target.
If the target is absent or blocked, visit the three directions in the plan's
fallback_order and return the first whose blocked flag is False.
After finding no clear direction, return "STOP", even when a target is given.
For example, when only LEFT is clear and target is FORWARD, return LEFT.
When all directions are blocked, return STOP for every possible target.
Use if/for/return statements. The for loop must iterate directly over a literal
tuple of three strings in the plan's order. Do NOT assign fallback_order to a
variable. Do NOT define direction constants or use tuple unpacking assignments.
Use no imports, calls, attributes, annotations, while loops or comprehensions.
Do not change obstacles. Include no Markdown fences, prose, examples or tests.
"""
ALLOWED_NODES = {
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.If,
    ast.For, ast.Assign, ast.Expr, ast.Constant, ast.Name, ast.Load, ast.Store,
    ast.Subscript, ast.Tuple, ast.List, ast.Compare, ast.Eq, ast.NotEq,
    ast.In, ast.NotIn, ast.Is, ast.IsNot, ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not, ast.Break, ast.Continue, ast.Pass,
}


def _restricted_function(source):
    if not isinstance(source, str) or not source.strip() or len(source) > 8000:
        raise ValueError("Expected a nonempty Python function of at most 8000 characters.")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ValueError("The developer reply is not valid Python source.") from error
    nodes = list(ast.walk(tree))
    if len(nodes) > 400 or any(type(node) not in ALLOWED_NODES for node in nodes):
        raise ValueError("Source contains syntax outside the restricted navigation subset.")
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("Only one top-level navigation function is permitted.")
    function = tree.body[0]
    args = function.args
    if (function.name != "navigate" or function.decorator_list or function.returns
            or len([node for node in nodes if isinstance(node, ast.FunctionDef)]) != 1
            or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg
            or [arg.arg for arg in args.args] != ["obstacles", "target"]
            or any(arg.annotation is not None for arg in args.args)
            or len(args.defaults) != 1 or not isinstance(args.defaults[0], ast.Constant)
            or args.defaults[0].value is not None):
        raise ValueError("Expected the exact signature navigate(obstacles, target=None).")
    loops = [node for node in nodes if isinstance(node, ast.For)]
    if len(loops) > 1:
        raise ValueError("At most one bounded direction loop is permitted.")
    for node in nodes:
        if isinstance(node, ast.Constant) and not (
                node.value is None or type(node.value) in (bool, str)):
            raise ValueError("Only strings, booleans and None are permitted constants.")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Special Python names are not navigation variables.")
        if isinstance(node, ast.Subscript) and not isinstance(node.ctx, ast.Load):
            raise ValueError("The function must not change its input dictionary.")
        if isinstance(node, ast.Assign) and (
                len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name)
                or node.targets[0].id in {"obstacles", "target"}):
            raise ValueError("Assignments must target a single local variable.")
        if isinstance(node, ast.Expr) and not (
                isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            raise ValueError("Standalone expressions are limited to docstrings.")
    for loop in loops:
        if (not isinstance(loop.target, ast.Name)
                or loop.target.id in {"obstacles", "target"}
                or not isinstance(loop.iter, (ast.Tuple, ast.List))
                or len(loop.iter.elts) != 3
                or any(not isinstance(item, ast.Constant) or not isinstance(item.value, str)
                       for item in loop.iter.elts)
                or {item.value for item in loop.iter.elts} != MOVES):
            raise ValueError("A loop must visit the three literal movement directions once each.")
    namespace = {}
    try:
        # This is a finite navigation subset, not a general Python sandbox.
        exec(compile(tree, "<checked-navigation>", "exec"), {"__builtins__": {}}, namespace)
    except (SyntaxError, ValueError, TypeError) as error:
        raise ValueError("The restricted function could not be compiled.") from error
    return namespace["navigate"]


def check_code(source, plan):
    if not validate_plan(plan):
        raise ValueError("A validated navigation plan is required.")
    navigate = _restricted_function(source)
    rows = []
    for flags in product((False, True), repeat=3):
        obstacles = dict(zip(("FORWARD", "LEFT", "RIGHT"), flags))
        clear = [move for move in plan["fallback_order"] if not obstacles[move]]
        for target in (None, "FORWARD", "LEFT", "RIGHT"):
            expected = target if target in clear else (clear[0] if clear else "STOP")
            supplied = obstacles.copy()
            try:
                actual = navigate(supplied, target)
                default_actual = navigate(supplied) if target is None else actual
            except Exception as error:
                raise ValueError(f"Navigation failed for obstacles={obstacles}, target={target}.") from error
            if (type(actual) is not str or actual != expected
                    or default_actual != expected or supplied != obstacles):
                raise ValueError(f"Plan mismatch for obstacles={obstacles}, target={target}: "
                                 f"expected {expected}, received {actual!r}.")
            rows.append({"obstacles": obstacles.copy(), "target": target,
                         "expected": expected, "actual": actual})
    return rows


def validate_code(source, plan):
    try:
        check_code(source, plan)
    except (ValueError, TypeError, RecursionError):
        return False
    return True


def run_developer(plan, *, trace_folder=None):
    if not validate_plan(plan):
        raise ValueError("Developer input must be a validated navigation plan.")
    source = ask("developer", INSTRUCTIONS, plan, trace_folder=trace_folder)
    check_code(source, plan)
    return source
