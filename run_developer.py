"""Generate navigation code, accepting it only after all 32 cases pass."""

import argparse

from developer_agent import run_developer
from workspace_io import ROOT, read_json, save_text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true", help="Permit one local CPU-only Qwen call.")
    args = parser.parse_args(argv)
    if not args.allow_model:
        parser.error("Use --allow-model to generate code. No model was contacted.")
    plan = read_json(ROOT / "artifacts" / "plan.json")
    source = run_developer(plan, trace_folder=ROOT / "evidence" / "exchanges")
    save_text(ROOT / "navigation_logic.py", source)
    print("navigation_logic.py saved after 32 navigation cases passed.")


if __name__ == "__main__":
    main()
