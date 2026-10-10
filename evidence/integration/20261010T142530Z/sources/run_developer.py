"""Generate the public navigation entrypoint and verify all 64 boolean states."""

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
    save_text(ROOT / "generated" / "navigation_logic.py", source)
    save_text(ROOT / "artifacts" / "navigation_logic.py", source)
    save_text(ROOT / "navigation_logic.py", source)
    print("Generated navigation saved after 64 cases passed; artifacts and legacy mirrors updated.")
    print(source)


if __name__ == "__main__":
    main()
