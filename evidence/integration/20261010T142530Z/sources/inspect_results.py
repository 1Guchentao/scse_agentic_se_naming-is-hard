"""Recheck saved artifacts and their recorded local-model exchanges offline."""

import argparse
import hashlib
from pathlib import Path

from analyst_agent import INSTRUCTIONS as ANALYST_PROMPT, validate_requirements
from developer_agent import INSTRUCTIONS as DEVELOPER_PROMPT, check_code
from local_qwen import MODEL
from planner_agent import INSTRUCTIONS as PLANNER_PROMPT, validate_plan
from workspace_io import ROOT, decode_json, read_json, save_json


def text_digest(path):
    # Git may check text out with CRLF on Windows; hash a portable LF representation.
    text = Path(path).read_text(encoding="utf-8-sig")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _exchange(root, stage, context, output, prompt):
    candidates = sorted((root / "evidence" / "exchanges").glob(stage + "-*.json"), reverse=True)
    for path in candidates:
        record = read_json(path)
        if not isinstance(record, dict) or record.get("stage") != stage:
            continue
        request, response = record.get("request", {}), record.get("response", {})
        if not isinstance(request, dict) or not isinstance(response, dict):
            continue
        if request.get("model") != MODEL or request.get("stream") is not False:
            continue
        if request.get("keep_alive") != 0 or request.get("options") != {
                "num_gpu": 0, "num_thread": 2, "num_ctx": 2048,
                "num_predict": 768, "temperature": 0}:
            continue
        messages = request.get("messages")
        if (not isinstance(messages, list) or len(messages) != 2
                or messages[0] != {"role": "system", "content": prompt}
                or not isinstance(messages[1], dict) or set(messages[1]) != {"role", "content"}
                or messages[1]["role"] != "user"):
            continue
        try:
            supplied = messages[1]["content"] if stage == "analyst" else decode_json(messages[1]["content"])
            if supplied != context:
                continue
            message = response.get("message", {})
            generated = message.get("content") if isinstance(message, dict) else None
            if not isinstance(generated, str):
                continue
            matches = decode_json(generated) == output if stage in {"analyst", "planner"} else (
                generated.replace("\r\n", "\n").replace("\r", "\n") == output)
        except (ValueError, TypeError):
            continue
        if matches and response.get("done") is True and response.get("done_reason") != "length":
            return path.relative_to(root).as_posix()
    raise ValueError(f"No complete CPU-only {stage} exchange matches both the current input and output.")


def inspect(root=ROOT):
    root = Path(root)
    requirements = read_json(root / "artifacts" / "requirements.json")
    plan = read_json(root / "artifacts" / "plan.json")
    if not validate_requirements(requirements) or not validate_plan(plan):
        raise ValueError("Invalid requirement or plan artifact.")
    source = (root / "generated" / "navigation_logic.py").read_text(encoding="utf-8")
    for mirror in ("navigation_logic.py", "artifacts/navigation_logic.py"):
        if (root / mirror).read_text(encoding="utf-8") != source:
            raise ValueError(f"The accepted generated code and its mirror {mirror} differ.")
    cases = check_code(source, plan)
    brief = (root / "brief.txt").read_text(encoding="utf-8-sig")
    exchanges = {
        "analyst": _exchange(root, "analyst", brief, requirements, ANALYST_PROMPT),
        "planner": _exchange(root, "planner", requirements, plan, PLANNER_PROMPT),
        "developer": _exchange(root, "developer", plan, source, DEVELOPER_PROMPT),
    }
    tracked = ["brief.txt", "artifacts/requirements.json", "artifacts/plan.json",
               "navigation_logic.py", "generated/navigation_logic.py", "artifacts/navigation_logic.py",
               *exchanges.values()]
    return {
        "result": "PASS", "navigation_cases": len(cases),
        "scope": "All 64 combinations of six boolean fields, including 32 original optional-target states.",
        "excluded": ["Physical robot testing", "Route completion", "Missing/non-boolean sensor fields"],
        "multiple_goals": "First clear indicated goal in FORWARD, LEFT, RIGHT order.",
        "original_helper": "AST-identical to the previous-stage navigation function.",
        "context_isolation": "Only the preceding validated artifact is supplied as each user message.",
        "exchanges": exchanges,
        "hash_convention": "SHA-256 of UTF-8 text with BOM removed and newlines normalized to LF.",
        "sha256": {path: text_digest(root / path) for path in tracked},
        "cases": cases,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="store_true", help="Refresh evidence/verification.json after checks pass.")
    args = parser.parse_args(argv)
    report = inspect()
    if args.save:
        save_json(ROOT / "evidence" / "verification.json", report)
    print(f"PASS: {report['navigation_cases']} navigation cases; all three recorded model exchanges match.")
    print("Scope: valid single-step inputs only; no physical robot or whole-route claim.")


if __name__ == "__main__":
    main()
