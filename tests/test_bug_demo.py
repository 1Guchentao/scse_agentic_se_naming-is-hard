import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_bug_demo
from tests.test_agents import SOURCE
from workspace_io import read_json, save_text


class BugDemoTests(unittest.TestCase):
    def test_mutation_changes_one_branch_only(self):
        mutated, previous = run_bug_demo.inject_stop_bug(SOURCE)
        self.assertEqual(previous, 'return navigate(obstacles, "FORWARD")')
        self.assertEqual(mutated, SOURCE.replace(previous, 'return "STOP"', 1))
        self.assertEqual(mutated.count('return "STOP"'), SOURCE.count('return "STOP"') + 1)
        self.assertEqual(mutated.split("def decide_next_move")[0], SOURCE.split("def decide_next_move")[0])

    def test_test_process_error_still_restores_original_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "generated" / "navigation_logic.py"
            save_text(path, SOURCE)
            original = path.read_bytes()
            with patch("run_bug_demo.ROOT", root), patch("run_bug_demo.run_tests",
                    side_effect=[({"exit_code": 0}, "OK"), RuntimeError("synthetic test failure")]):
                with self.assertRaisesRegex(RuntimeError, "synthetic test failure"):
                    run_bug_demo.main()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(read_json(root / "evidence" / "testing_summary.json")["result"], "FAILED")


if __name__ == "__main__":
    unittest.main()
