"""Level 2: known-state tests, without contacting any model.

Based on the teacher's six-boolean example. Expected results come from the
brief and the retained FORWARD/LEFT/RIGHT policy, not from generated code.
"""

from itertools import product
import unittest

from developer_agent import load_decider
from workspace_io import ROOT


def sensor_state(blocked=(False, False, False), goals=(False, False, False)):
    fields = ("front_blocked", "left_blocked", "right_blocked",
              "goal_ahead", "goal_on_left", "goal_on_right")
    return dict(zip(fields, (*blocked, *goals)))


class GeneratedNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "generated" / "navigation_logic.py").read_text(encoding="utf-8")
        cls.decide_next_move = staticmethod(load_decider(source))

    def assert_action(self, state, expected):
        before = state.copy()
        actual = self.decide_next_move(state)
        self.assertIs(type(actual), str)
        self.assertEqual(actual, expected, state)
        self.assertEqual(state, before, "The navigation function changed its sensor input.")
        if actual != "STOP":
            blocked_key = {"FORWARD": "front_blocked", "LEFT": "left_blocked", "RIGHT": "right_blocked"}
            self.assertFalse(state[blocked_key[actual]], "A blocked direction was selected.")

    def test_teacher_example(self):
        self.assert_action(sensor_state(goals=(True, False, False)), "FORWARD")

    def test_clear_left_goal_beats_clear_front_fallback(self):
        self.assert_action(sensor_state(goals=(False, True, False)), "LEFT")

    def test_clear_right_goal_beats_clear_front_fallback(self):
        self.assert_action(sensor_state(goals=(False, False, True)), "RIGHT")

    def test_blocked_goal_uses_clear_fallback(self):
        self.assert_action(sensor_state((True, False, False), (True, False, False)), "LEFT")

    def test_all_blocked_stops_even_with_goal(self):
        self.assert_action(sensor_state((True, True, True), (True, True, True)), "STOP")

    def test_no_goal_uses_original_fallback_order(self):
        self.assert_action(sensor_state(), "FORWARD")
        self.assert_action(sensor_state((True, False, False)), "LEFT")
        self.assert_action(sensor_state((True, True, False)), "RIGHT")

    def test_multiple_goals_prefer_first_clear_goal(self):
        self.assert_action(sensor_state((True, False, False), (True, False, True)), "RIGHT")
        self.assert_action(sensor_state(goals=(True, True, True)), "FORWARD")

    def test_repeated_calls_do_not_retain_previous_state(self):
        self.assert_action(sensor_state(goals=(False, False, True)), "RIGHT")
        self.assert_action(sensor_state((True, True, True)), "STOP")
        self.assert_action(sensor_state(), "FORWARD")


def _case_test(blocked, goals):
    # Resolve the expected answer independently, before calling the generated function.
    moves = ("FORWARD", "LEFT", "RIGHT")
    safe_goals = [move for move, wall, goal in zip(moves, blocked, goals) if goal and not wall]
    safe_moves = [move for move, wall in zip(moves, blocked) if not wall]
    expected = (safe_goals or safe_moves or ["STOP"])[0]

    def test(self):
        self.assert_action(sensor_state(blocked, goals), expected)
    return test


for _flags in product((False, True), repeat=6):
    _bits = "".join("1" if flag else "0" for flag in _flags)
    setattr(GeneratedNavigationTests, "test_state_" + _bits, _case_test(_flags[:3], _flags[3:]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
