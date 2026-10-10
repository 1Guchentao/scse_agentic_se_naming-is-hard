"""Run the navigation agents, tests, reviews and four-world benchmarks."""

import argparse
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import subprocess
import sys

from analyst_agent import run_analyst
from benchmark_irsim import run_benchmark
from developer_agent import run_developer, run_developer_revision
from integration.ledger import check_preserved_sources, snapshot
from integration.model_session import GpuSession, HIDDEN, THREAD_ENV, bind_existing_agents
from integration.test_execution import execute_suite
from planner_agent import run_planner
from reviewer_agent import run_reviewer
from reviewer_benchmark_agent import run_benchmark_reviewer
from runner import run_simulation
from test_agent import run_test_agent
from workspace_io import ROOT, read_json, save_json, save_text

REPORTS = ("simulation_report.json", "test_report.json", "simulation_review.json",
           "irsim_benchmark_report.json", "benchmark_review.json")


def run_round(folder, brief, session, log, previous=None):
    folder.mkdir()
    exchanges = folder / "exchanges"

    def stage(name, operation):
        log.info("START %s", name)
        value = operation()
        log.info("FINISH %s", name)
        return value

    requirements = stage("Analyst", lambda: run_analyst(brief, trace_folder=exchanges))
    save_json(folder / "requirements.json", requirements)
    plan = stage("Planner", lambda: run_planner(requirements, trace_folder=exchanges))
    save_json(folder / "plan.json", plan)
    if previous is None:
        source = stage("Developer", lambda: run_developer(plan, trace_folder=exchanges))
        save_text(folder / "navigation_logic.py", source)
    else:
        source = stage("Developer revision", lambda: run_developer_revision(
            previous["source"], previous["reviews"], previous["benchmark"],
            requirements, plan, output_path=folder / "navigation_logic.py", trace_folder=exchanges))
    tests = stage("Test Agent", lambda: run_test_agent(
        requirements, plan, source, brief, ask=session.ask, trace_folder=exchanges))
    save_text(folder / "test_navigation.py", tests)
    passed = stage("Generated pytest", lambda: execute_suite(source, tests, folder / "pytest"))
    control = stage("Wrong-turn control", lambda: execute_suite(source, tests, folder / "wrong_turn", mutate=True))
    save_json(folder / "test_report.json", {"navigation": passed, "wrong_turn_control": control})
    simulation = stage("Logical simulation", lambda: run_simulation(source))
    save_json(folder / "simulation_report.json", simulation)
    review = stage("Simulation reviewer", lambda: run_reviewer(
        simulation, ask=session.ask, trace_folder=exchanges))
    save_json(folder / "simulation_review.json", review)
    benchmark = stage("IR-SIM benchmark", lambda: run_benchmark(source, folder / "worlds"))
    save_json(folder / "irsim_benchmark_report.json", benchmark)
    benchmark_review = stage("Benchmark reviewer", lambda: run_benchmark_reviewer(
        benchmark, ask=session.ask, trace_folder=exchanges))
    save_json(folder / "benchmark_review.json", benchmark_review)
    return {"source": source, "benchmark": benchmark,
            "reviews": {"simulation": review, "benchmark": benchmark_review}}


def run_pipeline(backend, device, port):
    check_preserved_sources()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = ROOT / "evidence/integration" / run_id
    folder.mkdir(parents=True, exist_ok=False)
    logger = logging.getLogger("navigation.integration")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    file_handler = logging.FileHandler(folder / "trace.log", encoding="utf-8")
    stream_handler = logging.StreamHandler(sys.stdout)
    for handler in (file_handler, stream_handler):
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
    record = {"run_id": run_id, "status": "running", "rounds": []}
    save_json(folder / "run.json", record)
    try:
        snapshot(folder)
        brief = (ROOT / "brief.txt").read_text(encoding="utf-8-sig")
        save_text(folder / "brief.txt", brief)
        with GpuSession(folder / "runtime", backend, device, port) as session:
            with bind_existing_agents(session):
                logger.info("Beginning original-code round")
                original = run_round(folder / "initial", brief, session, logger)
                record["rounds"].append("initial")
                logger.info("Beginning revision round with fresh agent and simulation results")
                revised = run_round(folder / "revision", brief, session, logger, original)
                record["rounds"].append("revision")
                if any(revised["reviews"][name]["needs_revision"] for name in ("simulation", "benchmark")):
                    raise ValueError("The revised round still needs attention; it was not published.")
        cleanup = read_json(folder / "runtime/cleanup.json")
        if not cleanup["service_stopped"] or not cleanup["port_closed"] or cleanup["monitor_fault"]:
            raise RuntimeError("Model session cleanup or resource monitoring failed.")
        check_preserved_sources()
        environment = {**os.environ, **THREAD_ENV, "MPLBACKEND": "Agg"}
        legacy = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-q"],
                                cwd=ROOT, env=environment, capture_output=True, text=True,
                                timeout=90, creationflags=HIDDEN)
        save_text(folder / "regression.log", legacy.stdout + legacy.stderr)
        if legacy.returncode:
            raise ValueError("Existing regression tests failed.")
        record["status"] = "passed"
        save_json(folder / "run.json", record)
        for name in REPORTS:
            save_json(ROOT / "artifacts" / name, read_json(folder / "revision" / name))
        save_text(ROOT / "generated/navigation_logic_revised.py", revised["source"])
        save_json(ROOT / "evidence/integration/latest.json",
                  {"run": folder.relative_to(ROOT).as_posix(), "status": "passed"})
        logger.info("Published accepted revision; temporary service is closed")
        return folder
    except BaseException as error:
        record.update(status="error", error=str(error))
        save_json(folder / "run.json", record)
        logger.exception("Pipeline stopped without publishing a new accepted result")
        raise
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--backend", choices=("auto", "vulkan"), default="vulkan")
    parser.add_argument("--device", type=int, default=1)
    parser.add_argument("--port", type=int, default=11523)
    args = parser.parse_args(argv)
    if not args.allow_model:
        parser.error("Real local inference requires --allow-model.")
    print(run_pipeline(args.backend, args.device, args.port))


if __name__ == "__main__":
    main()
