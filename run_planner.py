"""Generate the plan from this group's existing requirements."""

import argparse

from planner_agent import run_planner
from workspace_io import ROOT, read_json, save_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true", help="Permit one local CPU-only Qwen call.")
    args = parser.parse_args(argv)
    if not args.allow_model:
        parser.error("Use --allow-model to generate a new plan. No model was contacted.")
    requirement = read_json(ROOT / "artifacts" / "requirements.json")
    plan = run_planner(requirement, trace_folder=ROOT / "evidence" / "exchanges")
    save_json(ROOT / "artifacts" / "plan.json", plan)
    print("Validated plan saved to artifacts/plan.json.")
    print((ROOT / "artifacts" / "plan.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
