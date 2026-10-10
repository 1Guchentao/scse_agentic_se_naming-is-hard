"""Windows-only, explicitly approved local Qwen session with owned-process cleanup."""

import argparse
import csv
import ctypes
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener

from local_qwen import MODEL
from workspace_io import ROOT, save_json, save_text


def _memory_gib():
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong), ("free_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("free_virtual", ctypes.c_ulonglong),
                    ("extended", ctypes.c_ulonglong)]
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise RuntimeError("Could not check available memory.")
    return memory.available / (1024 ** 3)


def _model_processes():
    result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                            text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return [row[0] for row in csv.reader(io.StringIO(result.stdout))
            if row and ("ollama" in row[0].lower() or "llama" in row[0].lower())]


def _port_busy():
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", 11434)) == 0


def _api(path, data=None):
    body = None if data is None else json.dumps(data).encode()
    request = Request("http://127.0.0.1:11434" + path, data=body,
                      headers={"Content-Type": "application/json"})
    with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
        return json.loads(response.read())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--stage", choices=("both", "planner", "developer", "testing"), default="both",
                        help="'testing' runs all three real-agent smoke tests, sequentially.")
    parser.add_argument("--ollama", type=Path,
                        default=Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe")
    args = parser.parse_args(argv)
    if not args.allow_model:
        parser.error("--allow-model is required. No service was started.")
    if sys.platform != "win32":
        parser.error("This service-management helper is for Windows; offline checks are cross-platform.")
    if not args.ollama.is_file():
        parser.error("Ollama was not found. This helper never installs software or downloads a model.")
    if _model_processes() or _port_busy():
        parser.error("An existing model service or listener was found. It was not changed or stopped.")
    available = _memory_gib()
    if available < 4.5:
        parser.error(f"Only {available:.2f} GiB RAM is available; at least 4.5 GiB is required.")
    environment = os.environ.copy()
    environment.update({
        "CUDA_VISIBLE_DEVICES": "-1", "GGML_VK_VISIBLE_DEVICES": "-1", "OLLAMA_VULKAN": "0",
        "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_CONTEXT_LENGTH": "2048",
        "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_KEEP_ALIVE": "0",
        "OLLAMA_NO_CLOUD": "1", "OLLAMA_NOPRUNE": "1", "NO_PROXY": "localhost,127.0.0.1",
        "PYTHONIOENCODING": "utf-8",
    })
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    record = {
        "started_utc": datetime.now(timezone.utc).isoformat(), "model": MODEL,
        "free_ram_gib_before": round(available, 2), "inference_threads": 2, "gpu_layers": 0,
        "stages_completed": [], "result": "FAILED", "automatic_model_retries": 0,
    }
    stages = (("analyst", "planner", "developer") if args.stage == "testing" else
              ("planner", "developer") if args.stage == "both" else (args.stage,))
    record["stages_requested"] = list(stages)
    record["test_outputs"] = {}
    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    server = None
    with (evidence / "local_service.log").open("wb") as log:
        try:
            server = subprocess.Popen([str(args.ollama), "serve"], env=environment,
                                      stdout=log, stderr=subprocess.STDOUT,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 25
            while True:
                if server.poll() is not None:
                    raise RuntimeError("The owned Ollama service stopped during startup.")
                try:
                    record["ollama_version"] = _api("/api/version")["version"]
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Ollama startup timed out; no generation was attempted.")
                    time.sleep(0.5)
            models = _api("/api/tags")["models"]
            existing = next((item for item in models if item.get("name") == MODEL), None)
            if existing is None:
                raise RuntimeError("qwen2.5:3b is not installed. No download was attempted.")
            record["installed_model"] = {key: existing[key] for key in ("name", "digest", "size", "details")}
            for stage in stages:
                record["current_stage"] = stage
                if _api("/api/ps").get("models"):
                    raise RuntimeError("The previous model is still loaded; the next stage was not started.")
                if _memory_gib() < 3:
                    raise RuntimeError("Less than 3 GiB is available before the next model call.")
                print(f"Running {stage}: CPU only, two inference threads, one request.", flush=True)
                completed = subprocess.run(
                    [sys.executable, str(ROOT / f"{'test' if args.stage == 'testing' else 'run'}_{stage}.py"),
                     "--allow-model"],
                    cwd=ROOT, env=environment, timeout=150, capture_output=True,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW)
                if completed.stdout:
                    print(completed.stdout, end="", flush=True)
                if completed.stderr:
                    print(completed.stderr, end="", file=sys.stderr, flush=True)
                output_path = evidence / "smoke" / session_id / (stage + ".txt")
                save_text(output_path, completed.stdout + completed.stderr)
                record["test_outputs"][stage] = output_path.relative_to(ROOT).as_posix()
                completed.check_returncode()
                deadline = time.monotonic() + 15
                while _api("/api/ps").get("models"):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Model unload timed out; further work was stopped.")
                    time.sleep(0.5)
                record["stages_completed"].append(stage)
            if "developer" in stages:
                from inspect_results import inspect
                save_json(evidence / "verification.json", inspect())
                print("PASS: 64 navigation states and matching Analyst/Planner/Developer exchanges.", flush=True)
            record["result"] = "PASS"
        except Exception as error:
            record["failure_type"] = type(error).__name__
            raise
        finally:
            try:
                if server is not None and server.poll() is None:
                    try:
                        _api("/api/generate", {"model": MODEL, "keep_alive": 0})
                    except (OSError, ValueError):
                        pass
                    # The live Popen handle identifies our server, not another user's service.
                    if server.poll() is None:
                        subprocess.run(["taskkill", "/PID", str(server.pid), "/T", "/F"],
                                       capture_output=True, timeout=15, check=True,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                        server.wait(timeout=10)
            except (OSError, subprocess.SubprocessError) as error:
                record["cleanup_error"] = type(error).__name__
            record["finished_utc"] = datetime.now(timezone.utc).isoformat()
            record["remaining_model_processes"] = _model_processes()
            record["port_11434_still_listening"] = _port_busy()
            record["cleanup_ok"] = not record["remaining_model_processes"] and not record["port_11434_still_listening"]
            save_json(evidence / "local_run.json", record)
            session_name = record["started_utc"].replace(":", "").replace("+", "_") + ".json"
            save_json(evidence / "sessions" / session_name, record)
    if not record["cleanup_ok"]:
        raise RuntimeError("Cleanup could not be confirmed. Inspect evidence/local_run.json before any further run.")
    print("Finished. The temporary model service is closed.")


if __name__ == "__main__":
    main()
