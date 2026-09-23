"""Try one next-action decision using the saved, verified model code."""

import argparse

from developer_agent import _restricted_function
from inspect_results import inspect
from workspace_io import ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocked", nargs="*", choices=("FORWARD", "LEFT", "RIGHT"), default=[])
    parser.add_argument("--target", choices=("FORWARD", "LEFT", "RIGHT"))
    args = parser.parse_args(argv)
    inspect()
    source = (ROOT / "navigation_logic.py").read_text(encoding="utf-8")
    navigate = _restricted_function(source)
    obstacles = {move: move in args.blocked for move in ("FORWARD", "LEFT", "RIGHT")}
    print(navigate(obstacles, args.target))


if __name__ == "__main__":
    main()
