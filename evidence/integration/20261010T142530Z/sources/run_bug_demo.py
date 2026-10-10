"""Record a real baseline -> injected bug -> restored test cycle."""

from datetime import datetime, timezone
import ast
import hashlib
import os
import subprocess
import sys

from workspace_io import ROOT, save_json, save_text


def run_tests(folder, phase):
    command = [sys.executable, str(ROOT / "test_generated_navigation_logic.py")]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    log = result.stdout + result.stderr
    save_text(folder / (phase + ".txt"), log)
    return {"exit_code": result.returncode, "log": (folder / (phase + ".txt")).relative_to(ROOT).as_posix()}, log


def inject_stop_bug(source):
    tree = ast.parse(source)
    wrapper = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == "decide_next_move")
    for node in ast.walk(wrapper):
        if (isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
                and len(node.value.args) == 2 and isinstance(node.value.args[1], ast.Constant)
                and node.value.args[1].value == "FORWARD"):
            segment = ast.get_source_segment(source, node)
            if not segment or source.count(segment) != 1:
                raise ValueError("Cannot identify one unique forward-goal return for the demonstration.")
            return source.replace(segment, 'return "STOP"', 1), segment
    raise ValueError("No suitable forward-goal branch found. Nothing was changed.")


def main():
    path = ROOT / "generated" / "navigation_logic.py"
    original = path.read_bytes()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = ROOT / "evidence" / "testing" / stamp
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "result": "FAILED",
              "scope": "One deliberately injected wrong action; not a complete mutation-testing campaign.",
              "file": "generated/navigation_logic.py",
              "original_sha256_bytes": hashlib.sha256(original).hexdigest()}
    try:
        report["baseline"], _ = run_tests(folder, "baseline")
        if report["baseline"]["exit_code"] != 0:
            raise RuntimeError("Baseline tests failed. No bug was inserted.")
        mutated, previous = inject_stop_bug(original.decode("utf-8"))
        report["mutation"] = {"before": previous, "after": 'return "STOP"',
                              "description": "Stop incorrectly when a forward goal is clear."}
        try:
            save_text(path, mutated)
            report["mutated_sha256_bytes"] = hashlib.sha256(path.read_bytes()).hexdigest()
            report["with_bug"], output = run_tests(folder, "with_bug")
            if (report["with_bug"]["exit_code"] == 0
                    or "AssertionError" not in output or "FAIL: test_teacher_example" not in output):
                raise RuntimeError("The known-state assertion did not demonstrate this bug.")
        finally:
            path.write_bytes(original)
        report["restored"], _ = run_tests(folder, "restored")
        report["restored_sha256_bytes"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if report["restored"]["exit_code"] != 0 or path.read_bytes() != original:
            raise RuntimeError("Restoration did not pass both the tests and byte-identity check.")
        report["result"] = "PASS"
    except Exception as error:
        report["failure"] = str(error)
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save_json(folder / "summary.json", report)
        save_json(ROOT / "evidence" / "testing_summary.json", report)
    print("PASS: baseline passed, the deliberate bug failed assertions, restored code passed.")
    print("Evidence: " + folder.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
