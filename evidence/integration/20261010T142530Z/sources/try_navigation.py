"""Try one next-action decision using the saved, verified model code."""

import argparse

from developer_agent import load_decider
from inspect_results import inspect
from workspace_io import ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocked", nargs="*", choices=("FORWARD", "LEFT", "RIGHT"), default=[])
    parser.add_argument("--target", choices=("FORWARD", "LEFT", "RIGHT"))
    args = parser.parse_args(argv)
    inspect()
    source = (ROOT / "generated" / "navigation_logic.py").read_text(encoding="utf-8")
    decide_next_move = load_decider(source)
    state = {
        "front_blocked": "FORWARD" in args.blocked,
        "left_blocked": "LEFT" in args.blocked,
        "right_blocked": "RIGHT" in args.blocked,
        "goal_ahead": args.target == "FORWARD",
        "goal_on_left": args.target == "LEFT",
        "goal_on_right": args.target == "RIGHT",
    }
    print(decide_next_move(state))


if __name__ == "__main__":
    main()
