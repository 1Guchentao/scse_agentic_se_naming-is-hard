"""Offline fixtures test the integration machinery, not real model quality."""

from copy import deepcopy
from pathlib import Path

import pytest

from benchmark_irsim import WORLDS, summarise, validate_world
from integration.cases import scenarios
from integration.ledger import check_preserved_sources
from integration.model_session import GpuSession
from integration.review_contracts import shape, validate_review
from integration.test_execution import execute_suite
from reviewer_agent import measured_flag
from reviewer_benchmark_agent import build_deterministic_review
from runner import run_simulation
from test_agent import validate_test_code
from workspace_io import ROOT, read_json

SOURCE = (ROOT / "generated/navigation_logic.py").read_text(encoding="utf-8")
SUITE = (Path(__file__).parent / "fixtures/suite.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("state,expected", list(scenarios()))
def test_all_expected_actions(state, expected):
    from developer_agent import load_decider
    before = state.copy()
    assert load_decider(SOURCE)(state) == expected
    assert state == before


def world_row(name="world_easy.yaml", steps=150, reached=True, collision=False):
    efficient = reached and steps <= 200
    return {"world": name, "reached_goal": reached, "collision_or_done": collision,
            "steps_taken": steps, "max_steps_allowed": 300, "efficient_step_limit": 200,
            "efficiency_status": "efficient" if efficient else (
                "acceptable_but_inefficient" if reached else "failed"),
            "efficiency_passed": efficient, "final_pose": [1.0, 0.0, 0.0],
            "history_length": steps, "collision_observed": collision, "error": None}


def full_report():
    return summarise([world_row(name) for name in WORLDS])


def test_preserved_sources():
    assert len(check_preserved_sources()["original_python"]) == 17


def test_simulation_has_unique_states():
    report = run_simulation(SOURCE)
    assert report["total_scenarios"] == report["passed_scenarios"] == 64
    assert len({tuple(row["state"].values()) for row in report["results"]}) == 64
    assert measured_flag(report) is False


def test_simulation_detects_a_wrong_turn():
    report = run_simulation(SOURCE.replace('return direction', 'return "STOP"'))
    assert report["failed_scenarios"] > 0
    assert measured_flag(report) is True


def test_simulation_rejects_imports():
    with pytest.raises(ValueError):
        run_simulation("import os\n" + SOURCE)


@pytest.mark.parametrize("change", [
    {"total_scenarios": 0}, {"total_scenarios": True}, {"passed_scenarios": 63},
    {"success_rate": 0.5}, {"failed_scenarios": -1}, {"results": []},
])
def test_simulation_review_rejects_inconsistent_counts(change):
    report = run_simulation(SOURCE)
    report.update(change)
    with pytest.raises(ValueError):
        measured_flag(report)


def test_valid_generated_test_fixture():
    assert validate_test_code(SUITE) == SUITE


@pytest.mark.parametrize("source", [SUITE.replace("import pytest\n", ""),
                                   SUITE.replace("test_navigation(blocked", "test_navigation(self, blocked")])
def test_test_validator_rejects_incomplete_module(source):
    with pytest.raises(ValueError):
        validate_test_code(source)


def test_test_validator_bounds_parametrization_size():
    with pytest.raises(ValueError, match="eight"):
        validate_test_code(SUITE.replace("repeat=3", "repeat=100000"))


def test_test_agent_receives_exact_context(tmp_path):
    import json
    from test_agent import TEST_SCHEMA, run_test_agent
    requirements = read_json(ROOT / "artifacts/requirements.json")
    plan = read_json(ROOT / "artifacts/plan.json")
    requests = []
    def fake(stage, prompt, context, **options):
        requests.append((stage, context, options))
        return json.dumps({"test_code": SUITE})
    assert run_test_agent(requirements, plan, SOURCE, "fixture brief", ask=fake, trace_folder=tmp_path) == SUITE
    assert requests[0][0] == "test_agent"
    assert requests[0][1] == {"brief": "fixture brief", "requirements": requirements, "plan": plan, "code": SOURCE}
    assert requests[0][2]["response_shape"] == TEST_SCHEMA


@pytest.mark.parametrize("replacement", [
    "import os\n", "print('unexpected')\n", "while True: pass\n",
    "__x = 1\n", "x = state.__class__\n", "x = open('file')\n",
    "from pathlib import Path\n", "def test_skip():\n    pass\n",
])
def test_test_validator_rejects_extra_code(replacement):
    with pytest.raises(ValueError):
        validate_test_code(SUITE + replacement)


@pytest.mark.parametrize("source", ["", "```python\npass\n```", "assert True", "x" * 14001])
def test_test_validator_rejects_incomplete_suites(source):
    with pytest.raises((ValueError, SyntaxError)):
        validate_test_code(source)


def test_pytest_execution_and_control(tmp_path):
    baseline = execute_suite(SOURCE, SUITE, tmp_path / "baseline")
    control = execute_suite(SOURCE, SUITE, tmp_path / "control", mutate=True)
    assert baseline["passed"] == 64
    assert control["assertion_failures"] > 0
    assert control["passed"] < 64


def test_pytest_execution_requires_all_states(tmp_path):
    shortened = SUITE.replace("list(product((False, True), repeat=3))", "[(False, False, False)]")
    with pytest.raises(ValueError, match="64"):
        execute_suite(SOURCE, shortened, tmp_path / "partial")


def test_benchmark_denominator_includes_failures():
    rows = [world_row(name) for name in WORLDS]
    rows[-1] = world_row(WORLDS[-1], 300, reached=False)
    report = summarise(rows)
    assert report["success_rate"] == 0.75
    assert report["average_steps_taken"] == 187.5
    assert report["failed_worlds"] == 1


@pytest.mark.parametrize("rows", [[], [world_row()], [world_row()] * 4])
def test_benchmark_requires_all_worlds(rows):
    with pytest.raises(ValueError):
        summarise(rows)


def test_unknown_steps_are_not_invented():
    rows = [world_row(name) for name in WORLDS]
    rows[-1].update(steps_taken=None, reached_goal=False, efficiency_passed=False, error="fixture failure")
    report = summarise(rows)
    assert report["average_steps_taken"] is None
    assert build_deterministic_review(report)["needs_revision"] is True


def test_complete_benchmark_passes():
    review = build_deterministic_review(full_report())
    assert review["needs_revision"] is False


@pytest.mark.parametrize("changes", [
    {"total_worlds": 3}, {"success_rate": 0.5}, {"efficiency_rate": 0},
    {"average_steps_taken": 1}, {"results": []}, {"failed_worlds": 1},
])
def test_benchmark_review_rejects_forged_summary(changes):
    report = full_report()
    report.update(changes)
    assert build_deterministic_review(report)["needs_revision"] is True


@pytest.mark.parametrize("changes", [
    {"steps_taken": 250}, {"steps_taken": True}, {"reached_goal": "true"},
    {"collision_observed": True}, {"collision_observed": None},
    {"efficient_step_limit": 250}, {"error": "fixture error"}, {"max_steps_allowed": 500},
])
def test_benchmark_review_rejects_unreliable_world(changes):
    rows = [world_row(name) for name in WORLDS]
    rows[0].update(changes)
    assert build_deterministic_review(summarise(rows))["needs_revision"] is True


def test_failed_goal_is_reported_unsafe_when_terminal():
    rows = [world_row(name) for name in WORLDS]
    rows[0] = world_row(WORLDS[0], 100, reached=False, collision=True)
    review = build_deterministic_review(summarise(rows))
    assert not review["safety_passed"]
    assert not review["goal_completion_passed"]


def test_inefficient_success_stays_a_success():
    rows = [world_row(name, 201) for name in WORLDS]
    report = summarise(rows)
    review = build_deterministic_review(report)
    assert report["success_rate"] == 1 and report["inefficient_success_worlds"] == 4
    assert review["goal_completion_passed"] and not review["efficiency_passed"]


def test_missing_benchmark_is_not_a_pass():
    assert build_deterministic_review({})["needs_revision"]


def test_revision_handoff_and_saved_source(tmp_path, monkeypatch):
    import json
    import developer_agent
    adapter = '''def decide_next_move(state):
    blocked_paths = {"FORWARD": state["front_blocked"], "LEFT": state["left_blocked"], "RIGHT": state["right_blocked"]}
    if state["goal_ahead"] and not blocked_paths["FORWARD"]:
        return navigate(blocked_paths, "FORWARD")
    if state["goal_on_left"] and not blocked_paths["LEFT"]:
        return navigate(blocked_paths, "LEFT")
    if state["goal_on_right"] and not blocked_paths["RIGHT"]:
        return navigate(blocked_paths, "RIGHT")
    return navigate(blocked_paths)
'''
    captured = []
    def fake(stage, prompt, context, **options):
        captured.append((stage, context, options))
        return json.dumps({"adapter": adapter})
    monkeypatch.setattr(developer_agent, "ask", fake)
    plan = read_json(ROOT / "artifacts/plan.json")
    requirements = read_json(ROOT / "artifacts/requirements.json")
    source = developer_agent.run_developer_revision(SOURCE, {"fixture_review": True}, full_report(),
                requirements, plan, output_path=tmp_path / "revised.py", trace_folder=tmp_path)
    assert source == developer_agent.ORIGINAL_SOURCE.rstrip() + "\n\n" + adapter
    assert (tmp_path / "revised.py").read_text(encoding="utf-8") == source
    assert captured[0][0] == "developer_revision"
    assert set(captured[0][1]) == {"original_code", "review_notes", "benchmark_report", "requirements", "plan"}
    assert captured[0][2]["response_shape"] == developer_agent.REVISION_SCHEMA


def test_revision_rejects_unchanged_nested_adapter(tmp_path, monkeypatch):
    import ast
    import json
    import developer_agent
    adapter = ast.get_source_segment(SOURCE, ast.parse(SOURCE).body[1])
    monkeypatch.setattr(developer_agent, "ask", lambda *args, **kwargs: json.dumps({"adapter": adapter}))
    with pytest.raises(ValueError):
        developer_agent.run_developer_revision(SOURCE, {}, full_report(),
            read_json(ROOT / "artifacts/requirements.json"), read_json(ROOT / "artifacts/plan.json"),
            output_path=tmp_path / "revised.py")
    assert not (tmp_path / "revised.py").exists()


def test_review_schema_and_types():
    flags = {"needs_revision": False}
    good = {"issue": "None measured", "likely_cause": "All states passed",
            "recommendation": "Keep behavior", **flags}
    assert validate_review(good, flags) == good
    assert shape(flags)["additionalProperties"] is False
    for changed in ({**good, "needs_revision": "false"}, {**good, "extra": 1},
                    {**good, "issue": ""}, {**good, "needs_revision": True}):
        with pytest.raises(ValueError):
            validate_review(changed, flags)


def test_raw_world_cross_checks():
    report = world_row(steps=1)
    capture = {"goal": [1.0, 0.0], "poses": [{"pose": [0.0, 0.0, 0.0], "collision": False},
                                           {"pose": [1.0, 0.0, 0.0], "collision": False}],
               "collision_observed": False}
    validate_world(report, capture)
    for changed in ({"reached_goal": False}, {"steps_taken": 400}, {"final_pose": [8, 8, 0]},
                    {"efficiency_status": "failed"}, {"max_steps_allowed": 999}):
        with pytest.raises(ValueError):
            validate_world({**report, **changed}, capture)


def test_gpu_preflight_refuses_low_memory(tmp_path, monkeypatch):
    monkeypatch.setattr("integration.model_session.hardware",
                        lambda: {"available_ram_gib": 3.0, "gpu_free_mib": 5000, "gpu_temperature_c": 40})
    with pytest.raises(RuntimeError, match="4.5 GiB"):
        with GpuSession(tmp_path / "runtime", port=61523):
            pytest.fail("The service should not have started.")
    assert read_json(tmp_path / "runtime/cleanup.json")["service_stopped"] is True


@pytest.mark.parametrize("loaded", [[], [{"name": "qwen2.5:3b", "size": 100, "size_vram": 0}]])
def test_gpu_reply_cannot_hide_cpu_execution(tmp_path, monkeypatch, loaded):
    session = GpuSession(tmp_path)
    monkeypatch.setattr("integration.model_session.hardware",
                        lambda: {"available_ram_gib": 5.0, "gpu_free_mib": 5000, "gpu_temperature_c": 40})
    reply = {"done": True, "done_reason": "stop", "message": {"content": "fixture"}}
    monkeypatch.setattr(session, "http", lambda path, data=None, **kwargs:
                        reply if path == "/api/chat" else {"models": loaded})
    with pytest.raises(RuntimeError, match="GPU"):
        session.ask("fixture", "offline test", {}, trace_folder=tmp_path)
    assert read_json(tmp_path / "fixture.json")["status"] == "error"
