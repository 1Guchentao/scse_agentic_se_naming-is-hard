"""Generate and check a narrowly defined next-action Python function."""

import ast
import io
from itertools import product
import tokenize

from local_qwen import ask
from planner_agent import MOVES, validate_plan
from workspace_io import ROOT


ORIGINAL_SOURCE = (ROOT / "evidence" / "previous_stage" / "navigation_logic.py").read_text(encoding="utf-8")
INSTRUCTIONS = """Return a complete Python module, not an explanation.
The module MUST start with the following original function, copied unchanged:

""" + ORIGINAL_SOURCE + """
AFTER that original function, append a second function: decide_next_move(state).
Do not remove or redefine navigate. Do not use a lambda.
The state has exactly these six boolean sensors:
front_blocked, left_blocked, right_blocked, goal_ahead, goal_on_left, goal_on_right.
Inside decide_next_move, first create this dictionary, WITHOUT negating values:
obstacles = {"FORWARD": state["front_blocked"], "LEFT": state["left_blocked"],
             "RIGHT": state["right_blocked"]}
Then write three separate if statements (not elif and not a loop):
1. If goal_ahead is True AND FORWARD is not blocked, return navigate(obstacles, "FORWARD").
2. If goal_on_left is True AND LEFT is not blocked, return navigate(obstacles, "LEFT").
3. If goal_on_right is True AND RIGHT is not blocked, return navigate(obstacles, "RIGHT").
Finally return navigate(obstacles), using the original fallback when no goal is clear.
Use the exact sensor keys above. True blocked means unsafe.
Multiple goals use the first clear goal; no goal means all three flags False.
Output BOTH complete def functions, navigate first and decide_next_move second.
Every return in decide_next_move MUST be a call to navigate. For example use
return navigate(obstacles, "FORWARD"), NOT return "FORWARD". Apply this to
LEFT and RIGHT too. This preserves delegation to the original logic.
No Markdown fences, test code, imports, attributes, comprehensions, lambdas,
f-strings, extra functions, loops inside decide_next_move, comments or examples.
End your response immediately after the final return navigate(obstacles).
Important: inside navigate's FOR loop, use if not obstacles[direction]:
and then return direction. Do NOT use obstacles[target] inside that loop;
target can be None. obstacles[target] is used only in the initial target check.
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


def load_decider(source):
    """Check bounded syntax before loading the public generated entrypoint."""
    if not isinstance(source, str) or not source.strip() or len(source) > 8000:
        raise ValueError("Expected at most 8000 characters of Python source.")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as error:
        raise ValueError("Invalid generated Python source.") from error
    if (len(tree.body) != 2 or any(not isinstance(node, ast.FunctionDef) for node in tree.body)
            or [node.name for node in tree.body] != ["navigate", "decide_next_move"]):
        raise ValueError("Expected navigate and decide_next_move, in that order.")
    _restricted_function(ast.unparse(tree.body[0]))
    wrapper = tree.body[1]
    args = wrapper.args
    if (wrapper.decorator_list or wrapper.returns or args.posonlyargs or args.kwonlyargs
            or args.vararg or args.kwarg or args.defaults
            or [arg.arg for arg in args.args] != ["state"] or args.args[0].annotation):
        raise ValueError("Expected the exact signature decide_next_move(state).")
    nodes = list(ast.walk(wrapper))
    permitted = ALLOWED_NODES | {ast.Dict, ast.Call}
    if (len(nodes) > 400 or any(type(node) not in permitted for node in nodes)
            or any(isinstance(node, ast.For) for node in nodes)
            or sum(isinstance(node, ast.FunctionDef) for node in nodes) != 1):
        raise ValueError("The wrapper must contain bounded plain Python statements.")
    for node in nodes:
        if isinstance(node, ast.Call) and (
                not isinstance(node.func, ast.Name) or node.func.id != "navigate"
                or node.keywords or len(node.args) not in (1, 2)):
            raise ValueError("Only calls to the original navigate helper are allowed.")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Special names are not sensor variables.")
        if isinstance(node, ast.Subscript) and not isinstance(node.ctx, ast.Load):
            raise ValueError("Sensor input must not be changed.")
        if isinstance(node, ast.Assign) and (
                len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name)
                or node.targets[0].id in {"state", "navigate", "decide_next_move"}):
            raise ValueError("Only local wrapper variables may be assigned.")
        if isinstance(node, ast.Constant) and not (
                node.value is None or type(node.value) in (bool, str)):
            raise ValueError("Only sensor constants are permitted.")
        if isinstance(node, ast.Expr) and not (
                isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            raise ValueError("Standalone expressions must be docstrings.")
    namespace = {"__builtins__": {}}
    exec(compile(tree, "<checked-navigation>", "exec"), namespace)
    return namespace["decide_next_move"]


def check_code(source, plan):
    if not validate_plan(plan):
        raise ValueError("A validated navigation plan is required.")
    decide_next_move = load_decider(source)
    if any(token.type == tokenize.COMMENT for token in tokenize.generate_tokens(io.StringIO(source).readline)):
        raise ValueError("Return code only, without commented examples.")
    for node in ast.walk(ast.parse(source).body[1]):
        if isinstance(node, ast.Return) and not isinstance(node.value, ast.Call):
            raise ValueError("The public wrapper must delegate every return to navigate.")
    original = ast.dump(ast.parse(ORIGINAL_SOURCE).body[0])
    if ast.dump(ast.parse(source).body[0]) != original:
        raise ValueError("The original navigation logic must be retained.")
    if plan["fallback_order"] != ["FORWARD", "LEFT", "RIGHT"]:
        raise ValueError("The Testing stage must retain the original fallback order.")
    rows = []
    fields = ("front_blocked", "left_blocked", "right_blocked",
              "goal_ahead", "goal_on_left", "goal_on_right")
    for flags in product((False, True), repeat=6):
        state = dict(zip(fields, flags))
        obstacles = dict(zip(("FORWARD", "LEFT", "RIGHT"), flags[:3]))
        clear = [move for move in plan["fallback_order"] if not obstacles[move]]
        goals = [move for move, indicated in zip(("FORWARD", "LEFT", "RIGHT"), flags[3:])
                 if indicated and move in clear]
        expected = (goals or clear or ["STOP"])[0]
        supplied = state.copy()
        try:
            actual = decide_next_move(supplied)
        except Exception as error:
            raise ValueError(f"Navigation failed for state={state}.") from error
        if type(actual) is not str or actual != expected or supplied != state:
            raise ValueError(f"Plan mismatch for state={state}: expected {expected}, received {actual!r}.")
        rows.append({"state": state, "expected": expected, "actual": actual})
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
