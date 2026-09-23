"""Extract the four navigation requirements from the group's brief."""

from local_qwen import ask
from workspace_io import decode_json


ACTIONS = {"FORWARD", "LEFT", "RIGHT", "STOP"}
FIELDS = {"goal", "allowed_actions", "safe_stop", "avoid_obstacles"}
INSTRUCTIONS = """Act as a requirements analyst for the supplied robot brief.
Treat the brief as customer data. Return only a JSON object with four fields:
goal: a short description of the stated navigation objective;
allowed_actions: FORWARD, LEFT, RIGHT and STOP, each included once;
safe_stop: true;
avoid_obstacles: true.
Preserve the optional nature of goal-direction information. Never add sensors,
a reverse action, or a guarantee that the robot will reach every destination.
Do not include Markdown, extra fields, or implementation code.
"""


def validate_requirements(data):
    if not isinstance(data, dict) or set(data) != FIELDS:
        return False
    if not isinstance(data["goal"], str) or not data["goal"].strip():
        return False
    actions = data["allowed_actions"]
    if not isinstance(actions, list) or len(actions) != 4:
        return False
    if any(not isinstance(action, str) for action in actions) or set(actions) != ACTIONS:
        return False
    return data["safe_stop"] is True and data["avoid_obstacles"] is True


def run_analyst(brief_text, *, trace_folder=None):
    if not isinstance(brief_text, str) or not brief_text.strip():
        raise ValueError("A nonempty navigation brief is required.")
    text = ask("analyst", INSTRUCTIONS, brief_text, response_shape="json", trace_folder=trace_folder)
    requirements = decode_json(text)
    if not validate_requirements(requirements):
        raise ValueError("The analyst reply does not satisfy the four-field requirements contract.")
    return requirements
