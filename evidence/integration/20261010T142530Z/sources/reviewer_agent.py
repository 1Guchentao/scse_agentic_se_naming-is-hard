"""Review all-state simulation failures without inventing measurements."""

from integration.review_contracts import request_review

INSTRUCTIONS = """Review the supplied navigation simulation summary.
Return JSON with exactly issue, likely_cause, recommendation, needs_revision.
The first three fields are concise, specific strings. needs_revision must
equal the provided measured flag. If all states passed, say no mismatch was
observed and suggest preserving the behavior during any readability revision.
Do not invent collisions, map results or problems that are not in this report.
"""


def measured_flag(report):
    total = report.get("total_scenarios")
    passed, failed = report.get("passed_scenarios"), report.get("failed_scenarios")
    if (type(total) is not int or total != 64 or type(passed) is not int
            or type(failed) is not int or passed + failed != total
            or not 0 <= passed <= total or not 0 <= failed <= total
            or report.get("success_rate") != passed / total):
        raise ValueError("Invalid all-state simulation summary.")
    rows = report.get("results")
    if not isinstance(rows, list) or len(rows) != total or sum(row.get("passed") is True for row in rows) != passed:
        raise ValueError("Simulation rows disagree with their summary.")
    return failed != 0


def run_reviewer(report, *, ask, trace_folder):
    flags = {"needs_revision": measured_flag(report)}
    compact = {name: value for name, value in report.items() if name != "results"}
    compact["failed_cases"] = [row for row in report["results"] if not row["passed"]]
    return request_review("simulation_reviewer", INSTRUCTIONS,
                          {"simulation": compact, "measured_flags": flags},
                          flags, ask, trace_folder)
