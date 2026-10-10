"""Verify the saved Integration evidence without starting a model."""

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

from analyst_agent import INSTRUCTIONS as ANALYST_PROMPT, validate_requirements
from benchmark_irsim import WORLDS, summarise, validate_world
from developer_agent import INSTRUCTIONS as DEVELOPER_PROMPT, ORIGINAL_SOURCE, REVISION_INSTRUCTIONS, REVISION_SCHEMA, check_code
from integration.cases import FIELDS, scenarios
from integration.ledger import check_preserved_sources, digest
from integration.model_session import MODEL
from integration.review_contracts import TEXT_FIELDS, shape, validate_review
from integration.test_execution import HOOK, RECORDER, WRONG_TURN
from main import REPORTS
from planner_agent import INSTRUCTIONS as PLANNER_PROMPT, PLAN_SCHEMA, validate_plan
from reviewer_agent import INSTRUCTIONS as REVIEW_PROMPT, measured_flag
from reviewer_benchmark_agent import INSTRUCTIONS as BENCHMARK_PROMPT, build_deterministic_review
from runner import run_simulation
from test_agent import INSTRUCTIONS as TEST_PROMPT, TEST_SCHEMA, validate_test_code
from workspace_io import ROOT, decode_json, read_json


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exchange(folder, stage, prompt, context, expected, response_shape=None, *, json_output=False):
    record = read_json(folder / "exchanges" / (stage + ".json"))
    request, response = record["request"], record["response"]
    require(record["status"] == "received" and record["stage"] == stage, "Incomplete model record.")
    require(request["model"] == MODEL and response["model"] == MODEL, "Unexpected model identity.")
    require(request["stream"] is False and request["keep_alive"] == "30s", "Unexpected model session settings.")
    require(request["options"] == {"num_gpu": 99, "num_thread": 2, "num_ctx": 4096,
                                   "num_batch": 64, "num_predict": 2200, "temperature": 0, "seed": 31},
            "Unexpected model options.")
    messages = request["messages"]
    require(len(messages) == 2 and messages[0] == {"role": "system", "content": prompt},
            "System prompt changed.")
    user = messages[1]
    require(set(user) == {"role", "content"} and user["role"] == "user", "Unexpected context envelope.")
    supplied = user["content"] if isinstance(context, str) else decode_json(user["content"])
    require(supplied == context, "Agent did not receive the recorded preceding artifacts.")
    require(request.get("format") == response_shape, "Model response schema changed.")
    require(response.get("done") is True and response.get("done_reason") != "length", "Truncated model reply.")
    require(record.get("unload_error") is None, "Model unload failed.")
    output = response["message"]["content"]
    parsed = decode_json(output) if json_output else output
    require(parsed == expected, "Saved artifact differs from its real model response.")
    loaded = [row for row in record["loaded_models"]["models"] if row["name"] == MODEL]
    require(bool(loaded) and loaded[0]["size_vram"] >= 0.9 * loaded[0]["size"], "GPU loading was not verified.")
    return output


def check_tests(folder, source, tests, summary, mutate):
    require((folder / "test_navigation.py").read_text(encoding="utf-8") == tests, "Executed pytest source differs.")
    expected_module = source + (WRONG_TURN if mutate else "") + RECORDER
    require((folder / "navigation_under_test.py").read_text(encoding="utf-8") == expected_module,
            "Tested navigation module differs.")
    require((folder / "conftest.py").read_text(encoding="utf-8") == HOOK, "Coverage recorder changed.")
    tree = ET.parse(folder / "results.xml").getroot()
    cases = tree.findall(".//testcase")
    failures = tree.findall(".//failure")
    require(len(cases) == 64 and not tree.findall(".//error") and not tree.findall(".//skipped"),
            "Tests did not execute 64 cases cleanly.")
    calls = read_json(folder / "calls.json")
    expected = {tuple(state[name] for name in FIELDS) for state, _ in scenarios()}
    require(all(isinstance(state, dict) and set(state) == set(FIELDS) for state in calls), "Invalid observed state.")
    require({tuple(state[name] for name in FIELDS) for state in calls} == expected, "State coverage is incomplete.")
    require(bool(failures) == mutate and all("AssertionError" in (node.text or "") for node in failures),
            "Wrong-turn control was not detected by assertions.")
    expected_summary = {"tests": 64, "passed": 64 - len(failures), "assertion_failures": len(failures),
                        "distinct_states": 64, "exit_code": 1 if mutate else 0,
                        "control": "swapped turns" if mutate else None}
    require(summary == expected_summary, "Test summary differs from executed JUnit evidence.")
    require((folder / "console.log").is_file(), "Missing pytest console output.")


def inspect_run(folder):
    check_preserved_sources()
    folder = Path(folder).resolve()
    require(folder.is_relative_to(ROOT / "evidence/integration"), "Run path is outside integration evidence.")
    run = read_json(folder / "run.json")
    require(run["status"] == "passed" and run["rounds"] == ["initial", "revision"], "The run is not complete.")
    hashes = read_json(folder / "source_hashes.json")
    for name, expected in hashes.items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe source record path.")
        require(digest(ROOT / relative) == expected, f"Source changed after the run: {name}")
        require(digest(folder / "sources" / relative) == expected, "Source snapshot differs.")
    brief = (ROOT / "brief.txt").read_text(encoding="utf-8-sig")
    require((folder / "brief.txt").read_text(encoding="utf-8") == brief, "Brief changed.")
    previous = None
    summaries = []
    for round_name in run["rounds"]:
        part = folder / round_name
        requirements, plan = read_json(part / "requirements.json"), read_json(part / "plan.json")
        require(validate_requirements(requirements) and validate_plan(plan), "Invalid requirements or plan.")
        source = (part / "navigation_logic.py").read_text(encoding="utf-8")
        check_code(source, plan)
        exchange(part, "analyst", ANALYST_PROMPT, brief, requirements, "json", json_output=True)
        exchange(part, "planner", PLANNER_PROMPT, requirements, plan, PLAN_SCHEMA, json_output=True)
        if previous is None:
            exchange(part, "developer", DEVELOPER_PROMPT, plan, source)
        else:
            context = {"original_code": previous["source"], "review_notes": previous["reviews"],
                       "benchmark_report": previous["benchmark"], "requirements": requirements, "plan": plan}
            raw = decode_json(read_json(part / "exchanges/developer_revision.json")["response"]["message"]["content"])
            exchange(part, "developer_revision", REVISION_INSTRUCTIONS, context, raw, REVISION_SCHEMA, json_output=True)
            require(source == ORIGINAL_SOURCE.rstrip() + "\n\n" + raw["adapter"].rstrip() + "\n", "Revision assembly differs.")
            require(source.strip() != previous["source"].strip(), "Revision did not change the adapter.")
        tests = (part / "test_navigation.py").read_text(encoding="utf-8")
        validate_test_code(tests)
        exchange(part, "test_agent", TEST_PROMPT, {"brief": brief, "requirements": requirements,
                                                 "plan": plan, "code": source},
                 {"test_code": tests}, TEST_SCHEMA, json_output=True)
        test_report = read_json(part / "test_report.json")
        check_tests(part / "pytest", source, tests, test_report["navigation"], False)
        check_tests(part / "wrong_turn", source, tests, test_report["wrong_turn_control"], True)
        simulation = read_json(part / "simulation_report.json")
        require(simulation == run_simulation(source), "Stored logical simulation differs from current decisions.")
        review = read_json(part / "simulation_review.json")
        flags = {"needs_revision": measured_flag(simulation)}
        validate_review(review, flags)
        compact = {key: value for key, value in simulation.items() if key != "results"}
        compact["failed_cases"] = [row for row in simulation["results"] if not row["passed"]]
        exchange(part, "simulation_reviewer", REVIEW_PROMPT, {"simulation": compact, "measured_flags": flags},
                 review, shape(flags), json_output=True)
        benchmark = read_json(part / "irsim_benchmark_report.json")
        rows = []
        for world in WORLDS:
            directory = part / "worlds" / Path(world).stem
            require(digest(directory / "test_irsim_with_agent.py", binary=True) ==
                    digest(ROOT / "test_irsim_with_agent.py", binary=True), "Teacher script copy differs.")
            require(digest(directory / "irsim_worlds" / world, binary=True) ==
                    digest(ROOT / "irsim_worlds" / world, binary=True), "World copy differs.")
            require((directory / "generated/navigation_logic.py").read_text(encoding="utf-8") == source,
                    "Simulated navigation differs.")
            raw = read_json(directory / "artifacts/irsim_report.json")
            capture = read_json(directory / "capture.json")
            validate_world(raw, capture)
            for name in ("route.gif", "route.png", "console.log"):
                require((directory / name).stat().st_size > 0, "Missing visual or console evidence.")
            rows.append({"world": world, **raw, "collision_observed": capture["collision_observed"], "error": None})
        require(benchmark == summarise(rows), "Benchmark summary differs from raw world results.")
        require(benchmark == read_json(part / "worlds/irsim_benchmark_report.json"), "Benchmark mirror differs.")
        benchmark_review = read_json(part / "benchmark_review.json")
        deterministic = build_deterministic_review(benchmark)
        flags = {key: value for key, value in deterministic.items() if type(value) is bool}
        validate_review(benchmark_review, flags)
        exchange(part, "benchmark_reviewer", BENCHMARK_PROMPT,
                 {"benchmark": benchmark, "deterministic_review": deterministic},
                 benchmark_review, shape(flags), json_output=True)
        require(len(list((part / "exchanges").glob("*.json"))) == 6, "Expected six independent model calls per round.")
        previous = {"source": source, "reviews": {"simulation": review, "benchmark": benchmark_review},
                    "benchmark": benchmark}
        summaries.append({"round": round_name, "generated_tests": 64,
                          "wrong_turn_failures": test_report["wrong_turn_control"]["assertion_failures"],
                          "goals": benchmark["goals_reached"], "average_steps": benchmark["average_steps_taken"]})
    require(not any(previous["reviews"][key]["needs_revision"] for key in ("simulation", "benchmark")),
            "The revised result still requires attention.")
    require((ROOT / "generated/navigation_logic_revised.py").read_text(encoding="utf-8") == previous["source"],
            "Published revised code differs.")
    for name in REPORTS:
        require(read_json(ROOT / "artifacts" / name) == read_json(folder / "revision" / name),
                "Published report differs: " + name)
    cleanup = read_json(folder / "runtime/cleanup.json")
    require(cleanup["service_stopped"] and cleanup["port_closed"] and cleanup["monitor_fault"] is None,
            "The model service did not close cleanly.")
    require(bool(cleanup["samples"]) and all(row["available_ram_gib"] >= 1.25 and row["gpu_temperature_c"] < 80
                                            for row in cleanup["samples"]), "Resource protection failed.")
    trace = (folder / "trace.log").read_text(encoding="utf-8")
    require(trace.count("FINISH Analyst") == 2 and trace.count("FINISH Benchmark reviewer") == 2,
            "Incomplete execution trace.")
    require("Ran 108 tests" in (folder / "regression.log").read_text(encoding="utf-8") and
            "\nOK\n" in (folder / "regression.log").read_text(encoding="utf-8"), "Previous tests did not pass.")
    return {"status": "passed", "model_exchanges": 12, "rounds": summaries}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path)
    args = parser.parse_args(argv)
    path = args.run or ROOT / read_json(ROOT / "evidence/integration/latest.json")["run"]
    import json
    print(json.dumps(inspect_run(path), indent=2))


if __name__ == "__main__":
    main()
