"""Optional regeneration of requirements; not needed for the submitted artifact."""

import argparse

from analyst_agent import run_analyst
from workspace_io import ROOT, save_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true", help="Permit one local CPU-only Qwen call.")
    args = parser.parse_args(argv)
    if not args.allow_model:
        parser.error("Regeneration requires --allow-model; existing requirements were not changed.")
    brief = (ROOT / "brief.txt").read_text(encoding="utf-8-sig")
    result = run_analyst(brief, trace_folder=ROOT / "evidence" / "exchanges")
    save_json(ROOT / "artifacts" / "requirements.json", result)
    print("Validated requirements saved. Regenerate downstream artifacts before using them.")


if __name__ == "__main__":
    main()
