"""Tie benchmark judgements to measured safety, completion and efficiency."""

from benchmark_irsim import summarise
from integration.review_contracts import request_review

INSTRUCTIONS = """Inspect the benchmark and the accompanying deterministic review.
Return exactly issue, likely_cause, recommendation, safety_passed,
goal_completion_passed, efficiency_passed, needs_revision.
Keep all four booleans identical to the measured flags. Use the three text
fields to explain actual evidence and a practical next step, not generic praise.
A passed four-world sample is not proof for arbitrary maps or physical robots.
Do not claim a shorter route or repaired bug when no such change was measured.
"""


def build_deterministic_review(report):
    flags = {"safety_passed": False, "goal_completion_passed": False,
             "efficiency_passed": False, "needs_revision": True}
    try:
        measured = summarise(report["results"])
        if any(report.get(key) != value for key, value in measured.items()):
            raise ValueError("Benchmark summary does not match world results.")
        complete = all(not row.get("error") and type(row.get("collision_or_done")) is bool
                       and type(row.get("collision_observed")) is bool
                       and type(row.get("reached_goal")) is bool
                       and type(row.get("steps_taken")) is int
                       and 1 <= row["steps_taken"] <= 300
                       and row.get("max_steps_allowed") == 300
                       and row.get("efficient_step_limit") == 200
                       and row.get("efficiency_passed") is (row["reached_goal"] and row["steps_taken"] <= 200)
                       for row in report["results"])
        flags["safety_passed"] = complete and all(
            not row["collision_observed"] and not (row["collision_or_done"] and not row["reached_goal"])
            for row in report["results"])
        flags["goal_completion_passed"] = complete and report["success_rate"] == 1.0
        flags["efficiency_passed"] = complete and report["inefficient_success_worlds"] == 0 and report["efficiency_rate"] == 1.0
        flags["needs_revision"] = not all(flags[key] for key in flags if key != "needs_revision")
        issues = []
        if not flags["safety_passed"]:
            issues.append("Unsafe or incomplete benchmark measurements")
        if not flags["goal_completion_passed"]:
            issues.append("Goal completion failure")
        if not flags["efficiency_passed"]:
            issues.append("Navigation failed or exceeded the efficiency limit")
        issue = "; ".join(issues) or "No failure measured in the four supplied worlds"
    except (KeyError, TypeError, ValueError):
        issue = "Missing or inconsistent benchmark measurements"
    return {"issue": issue, "likely_cause": "See the individual measured world records.",
            "recommendation": "Preserve working behavior and re-test any revision.", **flags}


def run_benchmark_reviewer(report, *, ask, trace_folder):
    deterministic = build_deterministic_review(report)
    flags = {key: value for key, value in deterministic.items() if type(value) is bool}
    return request_review("benchmark_reviewer", INSTRUCTIONS,
                          {"benchmark": report, "deterministic_review": deterministic},
                          flags, ask, trace_folder)
