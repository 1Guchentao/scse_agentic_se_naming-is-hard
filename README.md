# Robot Navigation: Planning and Development

Group: **naming-is-hard**

The saved plan and navigation code were generated locally with Qwen2.5:3b.
They pass all 32 valid next-action input combinations. The supporting project
also passes 32 offline regression tests on Python 3.10 and Python 3.12.

This project turns a short robot brief into a decision policy and a Python
next-action function. It continues the group's Requirements Engineering work
in this repository. The original `brief.txt` and `artifacts/requirements.json`
are retained; the Planner and Developer extend that work.

## Start with the saved results

Use Python 3.10 or newer. The project and its offline tests use only the Python
standard library: no `pip install`, cloud account, or running model is needed
to inspect the saved results.

From the repository folder on Windows:

```powershell
py -3.10 -m unittest discover -s tests -v
py -3.10 inspect_results.py
py -3.10 try_navigation.py --blocked FORWARD --target LEFT
```

The last example should print `LEFT`. With every direction blocked:

```powershell
py -3.10 try_navigation.py --blocked FORWARD LEFT RIGHT --target LEFT
```

The result should be `STOP`. On Linux or macOS, use `python3` instead of
`py -3.10`; the Windows service-management tests are skipped there. Run tests
from the repository root, not by opening an individual test file in an editor.

## How a decision is made

`navigate(obstacles, target=None)` receives three blocked flags:

```python
obstacles = {"FORWARD": True, "LEFT": False, "RIGHT": False}
```

`True` means that direction is blocked. An optional target is `FORWARD`, `LEFT`,
or `RIGHT`; `FORWARD` represents a goal ahead of the robot. An absent target
is `None`. The function prefers a clear target, otherwise uses the first clear
direction in the plan's `fallback_order`. It returns `STOP` when none is clear.

The plan stores this as two decisions, `CLEAR_TARGET` and `NO_CLEAR_TARGET`.
`TARGET` and `FIRST_CLEAR` describe how to select a direction; they are not new
robot actions. The only returned actions are `FORWARD`, `LEFT`, `RIGHT`, `STOP`.

This is a single-step navigation component, not a route planner. All 32 valid
input combinations can be checked: eight obstacle patterns, each paired with
three target directions or no target. Those checks do not establish physical
robot safety, route completion, or behaviour for missing/non-boolean sensors.

## The agent handoffs

The Analyst converts `brief.txt` into the four-field requirement artifact. The
existing group artifact is used for this continuation; it is not relabelled
as a new Analyst model run.

The Planner receives only the validated requirement object in its user message.
Its system prompt defines the robot's input vocabulary and plan format. The
validated plan is saved to `artifacts/plan.json`. The Developer receives that
plan, not the brief or the Analyst conversation, and returns Python source for
`navigation_logic.py`.

Generated source is parsed before execution. The checker accepts a small Python
subset with one function and at most one loop over three literal directions.
Imports, calls, attribute access, unbounded loops, and input mutation are
rejected. It then compares every valid input against the plan. This restricted
checker is not intended as a general-purpose sandbox for arbitrary Python.

Each completed local-model response is recorded before stage validation in
`evidence/exchanges/`. Rejected replies do not replace an accepted artifact.
`inspect_results.py` checks that saved output matches recorded model text and
that each recorded input contains only its preceding artifact. It also reruns
the navigation cases. Records are inspectable project evidence, not an
independent attestation service.

The first Developer reply failed validation: it returned a supplied target
without testing whether that direction was blocked. That reply remains in the
exchange records but was never accepted as `navigation_logic.py`. After making
the safety condition explicit in the Developer prompt, a second real response
passed the checks. The final source is that response, without manual code
replacement. `evidence/sessions/` retains both the failed and successful local
sessions; both finished with their temporary services closed.

## Regenerate with local Qwen

Regeneration is optional and changes the saved artifacts. It needs an existing
Ollama installation and the already-installed `qwen2.5:3b` model. The project
does not download a model, contact a cloud API, or start inference on import.

On Windows, close any separately running Ollama service yourself before using:

```powershell
py -3.10 run_local_pipeline.py --allow-model
```

The helper refuses to start if another model process/listener exists or less
than 4.5 GiB RAM is available. It starts a private local service, calls Planner
then Developer sequentially with `num_gpu=0` and `num_thread=2`, unloads the
model between calls, and closes its own service on completion or failure.
There are no automatic model retries. `evidence/local_run.json` records the
outcome and cleanup checks; the machine-specific service log stays local.
To explicitly regenerate only the Developer from an existing accepted plan,
add `--stage developer`. A failed stage is never retried automatically.

The three stage entrypoints are `run_analyst.py`, `run_planner.py`, and
`run_developer.py`. Each requires `--allow-model` and an already-running local
service when used individually. The combined helper runs only Planner and
Developer because the group already has its requirement artifact. If the
requirements are regenerated, regenerate both downstream stages as well.

## Project files and source material

- `analyst_agent.py`, `planner_agent.py`, `developer_agent.py`: prompts, model calls, and validation.
- `run_analyst.py`, `run_planner.py`, `run_developer.py`: load and save each stage's artifact.
- `artifacts/`: requirements and accepted plan.
- `navigation_logic.py`: accepted Developer output, not a handwritten test fixture.
- `local_qwen.py`, `workspace_io.py`: local HTTP transport and complete-file writes.
- `inspect_results.py`, `try_navigation.py`: offline verification and a small decision example.
- `tests/`: synthetic, offline regression cases; these never count as real model results.
- `evidence/`: original exchanges, local-run metadata, and the navigation verification report.

The source revisions and preserved input identities are listed in
`evidence/source_materials.json`. The teacher's Plan and Develop PDF is included
unchanged. Its page 8 says September 25 at midnight, while the accompanying
assignment message says September 24 at midnight. Plan for the earlier date
and confirm the exact deadline/timezone in Moodle. One group member submits
the existing group repository link:

[1Guchentao/scse_agentic_se_naming-is-hard](https://github.com/1Guchentao/scse_agentic_se_naming-is-hard)

The previous Analyst implementation contained a cloud credential. Current
source removes it and uses local Qwen. The owner still needs to revoke that
credential because deleting it from current files does not remove exposure
from earlier Git history. No previously exposed credential is used here.
