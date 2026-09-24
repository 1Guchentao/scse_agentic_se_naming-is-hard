"""Turn the validated requirement artifact into a short decision policy."""

from analyst_agent import validate_requirements
from local_qwen import ask
from workspace_io import decode_json


MOVES = {"FORWARD", "LEFT", "RIGHT"}
DECISIONS = [
    {"when": "CLEAR_TARGET", "select": "TARGET"},
    {"when": "NO_CLEAR_TARGET", "select": "FIRST_CLEAR"},
]
STRATEGY = ("Prefer a clear goal direction first, otherwise use the first unblocked "
            "fallback direction, and STOP if no direction is clear.")
INSTRUCTIONS = """You are the Planner for a mobile robot navigation component.
Use only the validated requirements in the user message. The robot observes
blocked flags for FORWARD, LEFT and RIGHT, and an optional goal direction.
Choose a safe next action, not a complete route or a guarantee of arrival.
Return JSON with exactly these four fields:
strategy: one sentence explicitly saying to prefer a clear goal direction
          first, otherwise use the first unblocked fallback direction, and
          STOP if no direction is clear. Do not omit the goal preference;
decisions: [{"when":"CLEAR_TARGET","select":"TARGET"},
            {"when":"NO_CLEAR_TARGET","select":"FIRST_CLEAR"}];
fallback_order: ["FORWARD", "LEFT", "RIGHT"], retaining the previous stage's order;
stop_condition: "NO_CLEAR_EXIT".
CLEAR_TARGET means a goal direction is supplied and is not blocked.
NO_CLEAR_TARGET means the goal is absent or blocked. FIRST_CLEAR chooses the
first unblocked direction in fallback_order. STOP when all three are blocked.
TARGET and FIRST_CLEAR are decision selectors, not additional robot actions.
Do not add fields, conversation history, Markdown, or Python code.
"""
PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["strategy", "decisions", "fallback_order", "stop_condition"],
    "properties": {
        "strategy": {"enum": [STRATEGY]},
        "decisions": {
            "type": "array", "minItems": 2, "maxItems": 2,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["when", "select"],
                "properties": {
                    "when": {"enum": ["CLEAR_TARGET", "NO_CLEAR_TARGET"]},
                    "select": {"enum": ["TARGET", "FIRST_CLEAR"]},
                },
            },
        },
        "fallback_order": {
            "type": "array", "minItems": 3, "maxItems": 3,
            "items": {"enum": ["FORWARD", "LEFT", "RIGHT"]},
            "enum": [["FORWARD", "LEFT", "RIGHT"]],
        },
        "stop_condition": {"enum": ["NO_CLEAR_EXIT"]},
    },
}


def validate_plan(data):
    if not isinstance(data, dict) or set(data) != set(PLAN_SCHEMA["required"]):
        return False
    if data["strategy"] != STRATEGY:
        return False
    if data["decisions"] != DECISIONS:
        return False
    order = data["fallback_order"]
    if not isinstance(order, list) or len(order) != 3:
        return False
    if order != ["FORWARD", "LEFT", "RIGHT"]:
        return False
    return data["stop_condition"] == "NO_CLEAR_EXIT"


def run_planner(requirement, *, trace_folder=None):
    if not validate_requirements(requirement):
        raise ValueError("Planner input must be a validated four-field requirement artifact.")
    text = ask("planner", INSTRUCTIONS, requirement,
               response_shape=PLAN_SCHEMA, trace_folder=trace_folder)
    plan = decode_json(text)
    if not validate_plan(plan):
        raise ValueError("The generated plan failed its decision-policy checks.")
    return plan
