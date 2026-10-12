"""Repeat the initial plain-text requirements exercise with local Qwen."""

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from workspace_io import ROOT, read_json, save_json, save_text

PROMPT = """Read the customer brief as a requirements analyst.
Return a numbered list of 6 to 9 short software requirements in English.
Describe what the navigation component must do, not Python code or a design.
Include the three blocked-path inputs, optional goal-direction information,
safe preference for the goal, obstacle avoidance, safe stopping when all exits
are blocked, and later testing in multiple simulated environments.
Goal-direction information MAY be absent; do not require a goal sensor value.
Only FORWARD, LEFT, RIGHT and STOP are permitted output actions.
Do not invent speed limits, a map algorithm, extra sensors, or a fallback
priority that the customer did not specify. Return only the numbered list.
"""


def validate_text(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("The model must return nonempty text.")
    if chr(96) * 3 in text or text.lstrip().startswith(("{", "[")):
        raise ValueError("This initial exercise needs prose, not JSON or code.")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not 6 <= len(lines) <= 9:
        raise ValueError("Expected six to nine numbered requirements.")
    if any(not line.startswith(f"{number}. ") for number, line in enumerate(lines, 1)):
        raise ValueError("Requirements must be numbered consecutively.")
    return text


def render_output(replies):
    return "\n\n".join(f"RUN {number}\n{text}" for number, text in enumerate(replies, 1)) + "\n"


def verify_saved(folder):
    folder = Path(folder)
    record = read_json(folder / "run.json")
    if record["status"] != "passed" or not 2 <= record["runs"] <= 3:
        raise ValueError("No completed repeated exercise was recorded.")
    brief = (ROOT / "brief.txt").read_text(encoding="utf-8-sig")
    if (folder / "brief.txt").read_text(encoding="utf-8") != brief:
        raise ValueError("Recorded brief differs from the original.")
    saved_source = (folder / "source_brief_to_req.py").read_text(encoding="utf-8")
    if hashlib.sha256(saved_source.encode()).hexdigest() != record["source_sha256"]:
        raise ValueError("Source snapshot differs from its recorded identity.")
    replies = []
    for number in range(1, record["runs"] + 1):
        exchange = read_json(folder / "exchanges" / f"requirements_{number}.json")
        request, response = exchange["request"], exchange["response"]
        if request["model"] != "qwen2.5:3b" or response.get("model") != request["model"]:
            raise ValueError("Wrong model in the recorded exchange.")
        if request["messages"] != [{"role": "system", "content": PROMPT},
                                    {"role": "user", "content": brief}]:
            raise ValueError("Recorded prompt or input differs.")
        if exchange["status"] != "received" or response.get("done") is not True or response.get("done_reason") == "length":
            raise ValueError("The recorded response did not finish.")
        if exchange["unload_error"] is not None:
            raise ValueError("The model was not unloaded cleanly.")
        replies.append(validate_text(response["message"]["content"]))
    cleanup = read_json(folder / "runtime/cleanup.json")
    if not cleanup["service_stopped"] or not cleanup["port_closed"] or cleanup["monitor_fault"]:
        raise ValueError("The temporary service did not close cleanly.")
    expected = render_output(replies)
    if (folder / "robot_requirements.txt").read_text(encoding="utf-8") != expected:
        raise ValueError("Saved text is not the verbatim model output.")
    if (ROOT / "robot_requirements.txt").read_text(encoding="utf-8") != expected:
        raise ValueError("Published text differs from its recorded run.")
    if record["identical_text"] != (len(set(replies)) == 1):
        raise ValueError("Consistency summary differs from the actual replies.")
    return {"status": "passed", "runs": len(replies),
            "identical_text": len(set(replies)) == 1, "completed_at": record["completed_at"]}


def generate(runs, backend, device, port):
    from integration.model_session import GpuSession
    if not 2 <= runs <= 3:
        raise ValueError("Use two or three sequential requests.")
    started = datetime.now(timezone.utc)
    folder = ROOT / "evidence/requirements" / started.strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True, exist_ok=False)
    brief = (ROOT / "brief.txt").read_text(encoding="utf-8-sig")
    source = Path(__file__).read_text(encoding="utf-8")
    record = {"status": "running", "runs": runs, "started_at": started.isoformat(),
              "purpose": "Missing initial prose exercise completed on the recorded date; not an earlier run.",
              "source_sha256": hashlib.sha256(source.encode()).hexdigest()}
    save_text(folder / "brief.txt", brief)
    save_text(folder / "source_brief_to_req.py", source)
    save_json(folder / "run.json", record)
    try:
        replies = []
        with GpuSession(folder / "runtime", backend, device, port) as session:
            for number in range(1, runs + 1):
                print(f"Qwen requirements request {number}/{runs}", flush=True)
                reply = session.ask(f"requirements_{number}", PROMPT, brief,
                                    trace_folder=folder / "exchanges")
                replies.append(validate_text(reply))
        cleanup = read_json(folder / "runtime/cleanup.json")
        if not cleanup["service_stopped"] or not cleanup["port_closed"] or cleanup["monitor_fault"]:
            raise RuntimeError("Temporary model cleanup failed; output was not published.")
        record.update(status="passed", identical_text=len(set(replies)) == 1,
                      completed_at=datetime.now(timezone.utc).isoformat())
        output = render_output(replies)
        save_text(folder / "robot_requirements.txt", output)
        save_json(folder / "run.json", record)
        save_text(ROOT / "robot_requirements.txt", output)
        save_json(ROOT / "evidence/requirements/latest.json",
                  {"run": folder.relative_to(ROOT).as_posix(), "status": "passed"})
        return folder
    except BaseException as error:
        record.update(status="error", error=str(error),
                      completed_at=datetime.now(timezone.utc).isoformat())
        save_json(folder / "run.json", record)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--runs", type=int, choices=(2, 3), default=3)
    parser.add_argument("--backend", choices=("auto", "vulkan"), default="vulkan")
    parser.add_argument("--device", type=int, default=1)
    parser.add_argument("--port", type=int, default=11524)
    args = parser.parse_args(argv)
    if args.verify:
        folder = ROOT / read_json(ROOT / "evidence/requirements/latest.json")["run"]
    elif args.allow_model:
        folder = generate(args.runs, args.backend, args.device, args.port)
    else:
        parser.error("Use --verify for saved output, or --allow-model for real local requests.")
    import json
    print(json.dumps(verify_saved(folder), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

