"""Ask the local model for a pytest suite, then validate its source."""

import ast

from analyst_agent import validate_requirements
from developer_agent import check_code
from planner_agent import validate_plan
from workspace_io import decode_json

TEST_SCHEMA = {"type": "object", "additionalProperties": False,
               "required": ["test_code"], "properties": {"test_code": {"type": "string"}}}

INSTRUCTIONS = """Write one complete pytest module for the supplied navigation component.
Return JSON with one key test_code. Its value is the complete Python source
of the file, including imports and decorators, not only a function body.
Use exactly these imports:
import pytest
from itertools import product
from navigation_under_test import decide_next_move
Define FIELDS as the tuple:
("front_blocked", "left_blocked", "right_blocked",
 "goal_ahead", "goal_on_left", "goal_on_right").
Use two pytest.mark.parametrize decorators on one function
test_navigation(blocked, clear_moves, goals).
The first decorator parametrizes "blocked,clear_moves" with these eight rows:
((False,False,False), ("FORWARD","LEFT","RIGHT")),
((False,False,True), ("FORWARD","LEFT")),
((False,True,False), ("FORWARD","RIGHT")),
((False,True,True), ("FORWARD",)),
((True,False,False), ("LEFT","RIGHT")),
((True,False,True), ("LEFT",)),
((True,True,False), ("RIGHT",)),
((True,True,True), ()).
The second decorator parametrizes "goals" with list(product((False,True), repeat=3)).
These decorators must yield all 64 combinations, not just eight examples.
Build state = dict(zip(FIELDS, blocked + goals)) and save before = state.copy().
Build indicated = dict(zip(("FORWARD","LEFT","RIGHT"), goals)).
Build targets = [move for move in clear_moves if indicated[move]].
Expected action is (targets + list(clear_moves) + ["STOP"])[0].
Assert decide_next_move(state) equals that expected value, then assert state == before.
The explicit clear_moves table is the independent oracle. Never use the
navigation function itself to calculate its expected result.
No fixtures, skip/xfail, try/except, main block, file access, extra imports,
helper functions, loops apart from the bounded list comprehension, or examples.
There is no test class, self parameter, or nested test function.
The test_code string MUST begin with these three lines, in this order:
import pytest
from itertools import product
from navigation_under_test import decide_next_move
"""


def validate_test_code(source):
    if not isinstance(source, str) or not source.strip() or len(source) > 14000 or "```" in source:
        raise ValueError("Expected an unfenced pytest module of at most 14000 characters.")
    tree = ast.parse(source)
    allowed = {ast.Module, ast.Import, ast.ImportFrom, ast.alias, ast.Assign,
               ast.FunctionDef, ast.arguments, ast.arg, ast.Call, ast.Attribute,
               ast.Name, ast.Load, ast.Store, ast.Constant, ast.Tuple, ast.List,
               ast.Dict, ast.keyword, ast.Assert, ast.Compare, ast.Eq, ast.Subscript,
               ast.BinOp, ast.Add, ast.ListComp, ast.comprehension}
    nodes = list(ast.walk(tree))
    if len(nodes) > 1200 or any(type(node) not in allowed for node in nodes):
        raise ValueError("Unsupported syntax in generated tests.")
    imports = []
    for node in nodes:
        if isinstance(node, ast.Import):
            imports.extend(("import", alias.name, alias.asname) for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            imports.extend((node.module, alias.name, alias.asname) for alias in node.names)
            if node.level:
                raise ValueError("Relative imports are not permitted.")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("Private names are not permitted.")
        if isinstance(node, ast.Attribute) and ast.unparse(node) not in (
                "pytest.mark", "pytest.mark.parametrize", "state.copy"):
            raise ValueError("Only parametrization and a state copy may use attributes.")
        if isinstance(node, ast.Call) and ast.unparse(node.func) not in (
                "pytest.mark.parametrize", "state.copy", "product", "dict", "zip",
                "list", "decide_next_move"):
            raise ValueError("Unsupported function call in generated tests.")
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "product":
            if (len(node.args) != 1 or ast.literal_eval(node.args[0]) != (False, True)
                    or len(node.keywords) != 1 or node.keywords[0].arg != "repeat"
                    or ast.literal_eval(node.keywords[0].value) != 3):
                raise ValueError("The goal product must contain exactly eight boolean combinations.")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (str, bool, int)):
            raise ValueError("Unexpected literal in generated tests.")
    if sorted(imports) != sorted([("import", "pytest", None), ("itertools", "product", None),
                                  ("navigation_under_test", "decide_next_move", None)]):
        raise ValueError("The three required imports must be used without aliases.")
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != "test_navigation":
        raise ValueError("Expected one parametrized test_navigation function.")
    if len(functions[0].decorator_list) != 2:
        raise ValueError("Expected obstacle and goal parametrizations.")
    arguments = functions[0].args
    if ([arg.arg for arg in arguments.args] != ["blocked", "clear_moves", "goals"]
            or arguments.posonlyargs or arguments.kwonlyargs or arguments.defaults
            or arguments.vararg or arguments.kwarg):
        raise ValueError("The test must use exactly blocked, clear_moves and goals arguments.")
    if sum(isinstance(node, ast.Assert) for node in nodes) < 2:
        raise ValueError("Tests must assert the action and input preservation.")
    return source


def run_test_agent(requirements, plan, source, brief, *, ask, trace_folder):
    if not validate_requirements(requirements) or not validate_plan(plan):
        raise ValueError("Tests require validated requirements and plan.")
    check_code(source, plan)
    text = ask("test_agent", INSTRUCTIONS,
               {"brief": brief, "requirements": requirements, "plan": plan, "code": source},
               response_shape=TEST_SCHEMA, trace_folder=trace_folder)
    envelope = decode_json(text)
    if not isinstance(envelope, dict) or set(envelope) != {"test_code"}:
        raise ValueError("The Test Agent must return one complete test_code file.")
    return validate_test_code(envelope["test_code"])



