"""Evaluate every valid sensor state without a model or physics engine."""

import argparse
from pathlib import Path

from developer_agent import load_decider
from integration.cases import scenarios
from workspace_io import ROOT, save_json


def run_simulation(source):
    decide = load_decider(source)
    results = []
    for number, (state, expected) in enumerate(scenarios(), 1):
        supplied = state.copy()
        try:
            actual = decide(supplied)
            error = None
        except Exception as exception:
            actual, error = None, str(exception)
        passed = type(actual) is str and actual == expected and supplied == state
        results.append({"case": number, "state": state, "expected": expected,
                        "actual": actual, "input_unchanged": supplied == state,
                        "passed": passed, "error": error})
    count = sum(row["passed"] for row in results)
    return {"total_scenarios": len(results), "passed_scenarios": count,
            "failed_scenarios": len(results) - count, "success_rate": count / len(results),
            "results": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, default=ROOT / "generated/navigation_logic.py")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/simulation_report.json")
    args = parser.parse_args(argv)
    report = run_simulation(args.code.read_text(encoding="utf-8"))
    save_json(args.output, report)
    print(f"{report['passed_scenarios']}/{report['total_scenarios']} states passed.")
    return int(report["failed_scenarios"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
