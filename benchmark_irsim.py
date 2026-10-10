"""Run the teacher script unchanged, once for each supplied world."""

import argparse
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

from developer_agent import load_decider
from integration.model_session import HIDDEN, THREAD_ENV
from workspace_io import ROOT, read_json, save_json, save_text

WORLDS = ("world_easy.yaml", "world_medium.yaml", "world_hard.yaml", "world_custom.yaml")


def validate_world(report, capture):
    required = {"reached_goal", "collision_or_done", "steps_taken", "max_steps_allowed",
                "efficient_step_limit", "efficiency_status", "efficiency_passed",
                "final_pose", "history_length"}
    if not isinstance(report, dict) or not required <= set(report):
        raise ValueError("Missing teacher simulation measurements.")
    for name in ("reached_goal", "collision_or_done", "efficiency_passed"):
        if type(report[name]) is not bool:
            raise ValueError("World flags must be booleans.")
    steps = report["steps_taken"]
    if type(steps) is not int or not 1 <= steps <= 300 or report["history_length"] != steps:
        raise ValueError("Invalid step count.")
    if report["max_steps_allowed"] != 300 or report["efficient_step_limit"] != 200:
        raise ValueError("Teacher runtime limits changed.")
    efficient = report["reached_goal"] and steps <= 200
    status = "efficient" if efficient else (
        "acceptable_but_inefficient" if report["reached_goal"] else "failed")
    if report["efficiency_passed"] != efficient or report["efficiency_status"] != status:
        raise ValueError("Efficiency fields disagree with measured steps.")
    pose, goal = report["final_pose"], capture["goal"]
    if len(pose) != 3 or not all(type(value) in (int, float) and math.isfinite(value) for value in pose):
        raise ValueError("Invalid final pose.")
    if report["reached_goal"] != (math.dist(pose[:2], goal) <= 0.4):
        raise ValueError("Reported goal completion differs from measured distance.")
    if capture["poses"][-1]["pose"] != pose or len(capture["poses"]) not in (steps, steps + 1):
        raise ValueError("Recorded trajectory and teacher report disagree.")
    if capture["collision_observed"] != any(row["collision"] for row in capture["poses"]):
        raise ValueError("Collision observation is inconsistent.")
    return report


def summarise(results):
    if len(results) != 4 or [row["world"] for row in results] != list(WORLDS):
        raise ValueError("A benchmark must retain all four supplied worlds in order.")
    reached = sum(row.get("reached_goal") is True for row in results)
    efficient = sum(row.get("reached_goal") is True and row.get("efficiency_passed") is True
                    for row in results)
    steps = [row.get("steps_taken") for row in results]
    average = sum(steps) / 4 if all(type(value) is int for value in steps) else None
    return {"total_worlds": 4, "goals_reached": reached, "success_rate": reached / 4,
            "efficient_worlds": efficient, "inefficient_success_worlds": reached - efficient,
            "failed_worlds": 4 - reached, "efficiency_rate": efficient / 4,
            "average_steps_taken": average, "results": results}


def run_benchmark(source, output):
    load_decider(source)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for world in WORLDS:
        directory = output / Path(world).stem
        (directory / "generated").mkdir(parents=True)
        (directory / "irsim_worlds").mkdir()
        save_text(directory / "generated/navigation_logic.py", source)
        shutil.copyfile(ROOT / "test_irsim_with_agent.py", directory / "test_irsim_with_agent.py")
        shutil.copyfile(ROOT / "irsim_worlds" / world, directory / "irsim_worlds" / world)
        environment = {**os.environ, **THREAD_ENV, "MPLBACKEND": "Agg",
                       "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            process = subprocess.run(
                [sys.executable, "-B", "-m", "integration.capture",
                 str(directory / "test_irsim_with_agent.py"), "irsim_worlds/" + world],
                cwd=directory, env=environment, text=True, capture_output=True,
                timeout=120, creationflags=HIDDEN)
            save_text(directory / "console.log", process.stdout + process.stderr)
            if process.returncode:
                raise RuntimeError(f"Simulation exited with status {process.returncode}.")
            raw = read_json(directory / "artifacts/irsim_report.json")
            capture = read_json(directory / "capture.json")
            validate_world(raw, capture)
            if not (directory / "route.gif").is_file() or not (directory / "route.png").is_file():
                raise ValueError("Simulation visual evidence was not saved.")
            row = {"world": world, **raw, "collision_observed": capture["collision_observed"],
                   "error": None}
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
            row = {"world": world, "reached_goal": False, "efficiency_passed": False,
                   "steps_taken": None, "collision_or_done": True, "collision_observed": None,
                   "error": str(error)}
        results.append(row)
        print(f"{world}: goal={row['reached_goal']}, steps={row['steps_taken']}", flush=True)
    report = summarise(results)
    save_json(output / "irsim_benchmark_report.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, default=ROOT / "generated/navigation_logic.py")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run_benchmark(args.code.read_text(encoding="utf-8"), args.output)
    print(f"Reached {report['goals_reached']}/4 goals; mean steps: {report['average_steps_taken']}")
    return int(report["failed_worlds"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
