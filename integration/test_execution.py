"""Execute generated tests with coverage recording and a wrong-turn control."""

import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from developer_agent import load_decider
from integration.cases import FIELDS, scenarios
from integration.model_session import HIDDEN, THREAD_ENV
from test_agent import validate_test_code
from workspace_io import read_json, save_text

RECORDER = """
_recorded_decision = decide_next_move
recorded_states = []

def decide_next_move(state):
    recorded_states.append(state.copy())
    return _recorded_decision(state)
"""
WRONG_TURN = """
_correct_decision = decide_next_move

def decide_next_move(state):
    action = _correct_decision(state)
    return {"LEFT": "RIGHT", "RIGHT": "LEFT"}.get(action, action)
"""
HOOK = """import json
from pathlib import Path
import navigation_under_test

def pytest_sessionfinish(session, exitstatus):
    Path("calls.json").write_text(json.dumps(navigation_under_test.recorded_states), encoding="utf-8")
"""


def execute_suite(source, tests, folder, *, mutate=False):
    load_decider(source)
    validate_test_code(tests)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    save_text(folder / "test_navigation.py", tests)
    save_text(folder / "navigation_under_test.py", source + (WRONG_TURN if mutate else "") + RECORDER)
    save_text(folder / "conftest.py", HOOK)
    environment = {**os.environ, **THREAD_ENV, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                   "PYTHONDONTWRITEBYTECODE": "1"}
    environment.pop("PYTHONPATH", None)
    process = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "--junitxml=results.xml", "test_navigation.py"],
        cwd=folder, env=environment, text=True, capture_output=True, timeout=60,
        creationflags=HIDDEN)
    save_text(folder / "console.log", process.stdout + process.stderr)
    xml = ET.parse(folder / "results.xml").getroot()
    cases = xml.findall(".//testcase")
    failures = [case.find("failure") for case in cases if case.find("failure") is not None]
    errors = xml.findall(".//error")
    skips = xml.findall(".//skipped")
    calls = read_json(folder / "calls.json")
    expected = {tuple(state[name] for name in FIELDS) for state, _ in scenarios()}
    seen = {tuple(state.get(name) for name in FIELDS) for state in calls
            if isinstance(state, dict) and set(state) == set(FIELDS)}
    if len(cases) != 64 or seen != expected or errors or skips:
        raise ValueError("Generated suite must execute all 64 valid states without errors or skips.")
    if mutate:
        if process.returncode != 1 or not failures or not all(
                "AssertionError" in (failure.text or "") for failure in failures):
            raise ValueError("The wrong-turn control must fail through action assertions.")
    elif process.returncode != 0 or failures:
        raise ValueError("Generated navigation tests failed; see the saved console log.")
    return {"tests": len(cases), "passed": len(cases) - len(failures),
            "assertion_failures": len(failures), "distinct_states": len(seen),
            "exit_code": process.returncode, "control": "swapped turns" if mutate else None}
