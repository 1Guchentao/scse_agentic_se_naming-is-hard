import copy
from itertools import permutations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import analyst_agent
import developer_agent
import planner_agent
import run_developer
import run_planner
from workspace_io import ROOT, decode_json, read_json, save_json, save_text


# Synthetic fixtures exercise the implementation without contacting a model.
REQUIREMENTS = {
    "goal": "Choose a safe next direction.",
    "allowed_actions": ["FORWARD", "LEFT", "RIGHT", "STOP"],
    "safe_stop": True, "avoid_obstacles": True,
}
PLAN = {
    "strategy": planner_agent.STRATEGY,
    "decisions": copy.deepcopy(planner_agent.DECISIONS),
    "fallback_order": ["FORWARD", "LEFT", "RIGHT"],
    "stop_condition": "NO_CLEAR_EXIT",
}
SOURCE = '''def navigate(obstacles, target=None):
    if target is not None and not obstacles[target]:
        return target
    for direction in ["FORWARD", "LEFT", "RIGHT"]:
        if not obstacles[direction]:
            return direction
    return "STOP"


def decide_next_move(state):
    obstacles = {"FORWARD": state["front_blocked"],
                 "LEFT": state["left_blocked"], "RIGHT": state["right_blocked"]}
    if state["goal_ahead"] and not obstacles["FORWARD"]:
        return navigate(obstacles, "FORWARD")
    if state["goal_on_left"] and not obstacles["LEFT"]:
        return navigate(obstacles, "LEFT")
    if state["goal_on_right"] and not obstacles["RIGHT"]:
        return navigate(obstacles, "RIGHT")
    return navigate(obstacles)
'''


class RequirementTests(unittest.TestCase):
    def test_valid_requirement(self):
        self.assertTrue(analyst_agent.validate_requirements(REQUIREMENTS))

    def test_rejects_wrong_fields_types_and_actions(self):
        invalid = [None, [], {}, {**REQUIREMENTS, "history": "old chat"}]
        for field, values in {
            "goal": [None, "", "  ", 23],
            "allowed_actions": [None, "FORWARD", ["FORWARD"] * 4,
                                ["FORWARD", "LEFT", "RIGHT", "REVERSE"], [["FORWARD"]] * 4],
            "safe_stop": [False, 0, 1, "true"],
            "avoid_obstacles": [False, None, 1],
        }.items():
            invalid.extend({**REQUIREMENTS, field: value} for value in values)
        for data in invalid:
            with self.subTest(data=data):
                self.assertFalse(analyst_agent.validate_requirements(data))

    def test_analyst_checks_reply(self):
        with patch("analyst_agent.ask", return_value=json.dumps(REQUIREMENTS)):
            self.assertEqual(analyst_agent.run_analyst("A robot brief"), REQUIREMENTS)
        with patch("analyst_agent.ask", return_value="{}"):
            with self.assertRaises(ValueError):
                analyst_agent.run_analyst("A robot brief")

    def test_blank_brief_never_calls_model(self):
        with patch("analyst_agent.ask") as ask:
            with self.assertRaises(ValueError):
                analyst_agent.run_analyst(" ")
            ask.assert_not_called()


class PlannerTests(unittest.TestCase):
    def test_only_the_retained_fallback_order_is_valid(self):
        for order in permutations(PLAN["fallback_order"]):
            self.assertEqual(planner_agent.validate_plan({**PLAN, "fallback_order": list(order)}),
                             list(order) == ["FORWARD", "LEFT", "RIGHT"])

    def test_rejects_every_invalid_plan_field(self):
        invalid = [None, [], {}, {**PLAN, "extra": True}]
        for field, values in {
            "strategy": [None, 1, " ", "Choose the first unblocked direction for navigation"],
            "decisions": [None, [], list(reversed(PLAN["decisions"])),
                          [{"when": "CLEAR_TARGET", "select": "STOP"}, PLAN["decisions"][1]]],
            "fallback_order": [None, ["FORWARD"] * 3, ["LEFT", "RIGHT", "STOP"],
                               [["FORWARD"], "LEFT", "RIGHT"]],
            "stop_condition": [False, None, "GOAL_REACHED"],
        }.items():
            invalid.extend({**PLAN, field: value} for value in values)
        for data in invalid:
            with self.subTest(data=data):
                self.assertFalse(planner_agent.validate_plan(data))

    def test_planner_context_is_only_validated_requirements(self):
        with patch("planner_agent.ask", return_value=json.dumps(PLAN)) as ask:
            self.assertEqual(planner_agent.run_planner(REQUIREMENTS), PLAN)
            self.assertEqual(ask.call_args.args[2], REQUIREMENTS)
        with patch("planner_agent.ask") as ask:
            with self.assertRaises(ValueError):
                planner_agent.run_planner({**REQUIREMENTS, "conversation": []})
            ask.assert_not_called()

    def test_rejects_malformed_or_unvalidated_model_plan(self):
        for reply in ("```json\n{}\n```", "{}", "null", '{"strategy":"x","strategy":"y"}'):
            with self.subTest(reply=reply), patch("planner_agent.ask", return_value=reply):
                with self.assertRaises(ValueError):
                    planner_agent.run_planner(REQUIREMENTS)


class DeveloperTests(unittest.TestCase):
    def test_all_64_states_and_retained_helper(self):
        rows = developer_agent.check_code(SOURCE, PLAN)
        self.assertEqual(len(rows), 64)
        self.assertTrue(developer_agent.validate_code(SOURCE, PLAN))

    def test_wrong_but_valid_python_is_rejected(self):
        for source in (
            'def navigate(obstacles, target=None):\n    return "STOP"\n',
            'def navigate(obstacles, target=None):\n    return "FORWARD"\n',
            SOURCE.replace('"FORWARD", "LEFT", "RIGHT"', '"LEFT", "RIGHT", "FORWARD"'),
            SOURCE.replace('return target', 'return "STOP"'),
            SOURCE.replace('if target is not None and not obstacles[target]:', 'if target is not None:'),
            SOURCE.replace('return navigate(obstacles, "FORWARD")', 'return "STOP"'),
            SOURCE.split("\n\ndef decide_next_move")[0],
            SOURCE + '\n# Incorrect generated example\n',
        ):
            self.assertFalse(developer_agent.validate_code(source, PLAN))

    def test_rejects_unsafe_or_unbounded_source_before_execution(self):
        invalid = [
            'import os\n' + SOURCE,
            SOURCE + '\nprint("hello")',
            SOURCE.replace('return target', 'return str(target)'),
            SOURCE.replace('return target', 'return target.lower()'),
            SOURCE.replace('return target', 'obstacles[target] = False\n        return target'),
            SOURCE.replace('for direction in ["FORWARD", "LEFT", "RIGHT"]:', 'for direction in obstacles:'),
            SOURCE.replace('return target', 'while True:\n            pass'),
            SOURCE.replace('target=None', 'target="FORWARD"'),
            SOURCE.replace('navigate(', 'move('),
            '@dangerous\n' + SOURCE,
            '```python\n' + SOURCE + '```',
            'def navigate(obstacles, target=None):\n    return [x for x in obstacles]\n',
            'def navigate(obstacles, target=None):\n    def nested():\n        pass\n    return "STOP"',
            SOURCE.replace('return navigate(obstacles, "FORWARD")', 'return decide_next_move(state)'),
            SOURCE.replace('return navigate(obstacles, "FORWARD")', 'return open("secret.txt")'),
            SOURCE.replace('return navigate(obstacles, "FORWARD")', 'state["front_blocked"] = False'),
            SOURCE.replace('return navigate(obstacles, "FORWARD")', 'while True:\n            pass'),
        ]
        for source in invalid:
            with self.subTest(source=source):
                self.assertFalse(developer_agent.validate_code(source, PLAN))

    def test_developer_context_and_original_text_preserved(self):
        with patch("developer_agent.ask", return_value=SOURCE) as ask:
            self.assertEqual(developer_agent.run_developer(PLAN), SOURCE)
            self.assertEqual(ask.call_args.args[2], PLAN)

    def test_invalid_plan_never_calls_model(self):
        with patch("developer_agent.ask") as ask:
            with self.assertRaises(ValueError):
                developer_agent.run_developer({})
            ask.assert_not_called()


class FileAndRunnerTests(unittest.TestCase):
    def test_strict_json_rejects_duplicate_fields_and_nonfinite_numbers(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'):
            with self.assertRaises(ValueError):
                decode_json(text)

    def test_atomic_write_and_bom_read(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nested" / "data.json"
            save_json(path, REQUIREMENTS)
            self.assertEqual(read_json(path), REQUIREMENTS)
            save_text(path, "\ufeff" + json.dumps(PLAN))
            self.assertEqual(read_json(path), PLAN)
            self.assertEqual(list(path.parent.glob("*.part")), [])

    def test_invalid_plan_does_not_overwrite_previous_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save_json(root / "artifacts" / "requirements.json", REQUIREMENTS)
            save_json(root / "artifacts" / "plan.json", PLAN)
            with patch("run_planner.ROOT", root), patch("planner_agent.ask", return_value="{}"):
                with self.assertRaises(ValueError):
                    run_planner.main(["--allow-model"])
            self.assertEqual(read_json(root / "artifacts" / "plan.json"), PLAN)

    def test_invalid_code_does_not_overwrite_previous_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save_json(root / "artifacts" / "plan.json", PLAN)
            save_text(root / "navigation_logic.py", SOURCE)
            with patch("run_developer.ROOT", root), patch("developer_agent.ask", return_value="bad Python"):
                with self.assertRaises(ValueError):
                    run_developer.main(["--allow-model"])
            self.assertEqual((root / "navigation_logic.py").read_text(), SOURCE)

    def test_all_generation_entrypoints_require_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ("run_analyst.py", "run_planner.py", "run_developer.py",
                         "test_analyst.py", "test_planner.py", "test_developer.py"):
                result = subprocess.run([sys.executable, str(ROOT / name)], cwd=temp,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("--allow-model", result.stderr)

    def test_valid_runner_writes_under_project_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save_json(root / "artifacts" / "requirements.json", REQUIREMENTS)
            with patch("run_planner.ROOT", root), patch("planner_agent.ask", return_value=json.dumps(PLAN)):
                run_planner.main(["--allow-model"])
            with patch("run_developer.ROOT", root), patch("developer_agent.ask", return_value=SOURCE):
                run_developer.main(["--allow-model"])
            self.assertEqual(read_json(root / "artifacts" / "plan.json"), PLAN)
            self.assertEqual((root / "navigation_logic.py").read_text(), SOURCE)
            self.assertEqual((root / "generated" / "navigation_logic.py").read_text(), SOURCE)
            self.assertEqual((root / "artifacts" / "navigation_logic.py").read_text(), SOURCE)


if __name__ == "__main__":
    unittest.main()
