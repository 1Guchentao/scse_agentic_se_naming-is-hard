# Robot Navigation: Agent Pipeline and Testing

Group: **naming-is-hard**

This project turns a short robot brief into a decision policy and a Python
next-action function. It continues the group's Requirements Engineering work
and Plan and Develop work in this repository. For the Testing stage, all three
agents run again against the original brief and the preceding stage's output.
The original navigation function is retained inside a new public entrypoint.
Earlier artifacts are kept in `evidence/previous_stage/` and Git history.

The saved result passes 108 offline tests: 64 exhaustive state cases, eight
focused behavior tests and 36 supporting regression tests. The deliberate bug
caused 18 action assertions to fail; restoring the code returned all 72 behavior
tests to passing. Real agent responses and failure/restoration logs are included.
The full suite passed on Python 3.10.11 and 3.12.0. The recorded checks are in
`evidence/submission_audit.json`, with full offline logs in `evidence/offline/`.

## Start with the saved results

Use Python 3.10 or newer. The project and its offline tests use only the Python
standard library: no `pip install`, cloud account, or running model is needed
to inspect the saved results.

From the repository folder on Windows:

```powershell
py -3.10 -m unittest discover -v
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

Other programs call only `decide_next_move(state)`, from
`generated/navigation_logic.py`. A state has six boolean fields:

```python
state = {
    "front_blocked": True, "left_blocked": False, "right_blocked": False,
    "goal_ahead": False, "goal_on_left": True, "goal_on_right": False,
}
```

`True` in a blocked field means that direction is unsafe. A goal flag indicates
the goal's direction; all three goal flags being false represents no goal.
The original `navigate` function is an internal helper, not the public interface.
It still prefers a clear target, otherwise tries FORWARD, LEFT, RIGHT in order
and returns STOP when none is clear.

The brief does not specify simultaneous goal flags. For that case, this group
uses the first clear indicated goal in FORWARD, LEFT, RIGHT order. A blocked
goal never hides another clear goal. This tie-break is a documented extension,
not an extra requirement attributed to the teacher.

The plan stores this as two decisions, `CLEAR_TARGET` and `NO_CLEAR_TARGET`.
`TARGET` and `FIRST_CLEAR` describe how to select a direction; they are not new
robot actions. The only returned actions are `FORWARD`, `LEFT`, `RIGHT`, `STOP`.

This is a single-step navigation component, not a route planner. The behavior
suite checks all 64 boolean combinations, including the 32 states corresponding
to the original single-target interface. It adds eight focused tests for the
teacher's example, blocked goals, goal preference, fallback, multiple goals,
and repeated calls. These checks do not establish physical robot safety, route
completion, or behavior for missing/non-boolean sensors.

## The agent handoffs

The Analyst converts the unchanged `brief.txt` into the four-field requirement
artifact. Unlike the previous continuation, Testing includes a new real Analyst
run. `test_analyst.py` calls that agent normally, saves its validated output to
`artifacts/requirements.json`, and prints the result.

The Planner receives only the validated requirement object in its user message.
Its system prompt defines the robot's input vocabulary and plan format. The
validated plan is saved and displayed by `test_planner.py`. The Developer
receives only that plan as its user message. Its system prompt specifies the
new sensor interface and includes the old function that must be retained.
`test_developer.py` calls the Developer, checks both functions, saves the code,
and displays it. These three scripts require explicit model opt-in; importing
them or discovering the offline tests never starts inference.

The PDF names `artifacts/navigation_logic.py` on page 7 and
`generated/navigation_logic.py` in the final checklist on page 11. The latter
is the canonical runnable artifact. Both paths, and the legacy root path,
contain the same accepted Developer response. The verifier checks their identity.

Generated source is parsed before execution. The checker accepts a small Python
subset with the retained helper and the public wrapper. The helper has at most
one loop over three literal directions; the wrapper cannot contain a loop and
may call only that helper. Imports, attribute access, recursion, and input
mutation are rejected. All 64 states are then compared against the plan.
The helper's syntax tree must match its previous-stage snapshot. This restricted
checker is not intended as a general-purpose sandbox for arbitrary Python.

Each completed local-model response is recorded before stage validation in
`evidence/exchanges/`. Rejected replies do not replace an accepted artifact.
`inspect_results.py` checks that saved output matches recorded model text and
that each recorded input contains only its preceding artifact. It also reruns
the navigation cases. Records are inspectable project evidence, not an
independent attestation service.

The first Testing Developer response was rejected: it reversed blocked flags,
used non-existent sensor names and attempted a recursive lambda instead of
retaining the helper. That source was not executed or installed. The prompt
was clarified and the real pipeline rerun, without weakening the state tests.
The initial Planner explanation also said "both are blocked"; the strategy
field now uses a precise schema value saying STOP only if no direction is clear.
Original rejected replies and failed sessions remain in the evidence.
A later response passed the action checks but included an incorrect commented
example. It was replaced by a new Developer run, rather than editing the model
output by hand. The final acceptance checks reject commented examples and
require the wrapper to delegate its returns to the retained helper. One further
reply changed the helper's loop lookup from `direction` to `target`; the
retention check rejected it before it could replace the saved artifact.

## Showing that tests catch a bug

`test_generated_navigation_logic.py` calls only the public function and checks
expected actions derived independently from the brief and retained policy.
To run the required deliberate-error exercise:

```powershell
py -3.10 run_bug_demo.py
```

The script first requires a passing baseline. It then changes one real generated
branch to return STOP incorrectly when a forward goal is clear. The teacher's
example must fail with an assertion, not merely an import or syntax error.
A `finally` block restores the exact original bytes even if the test process
fails. The suite runs again and must pass after restoration.

`evidence/testing_summary.json` links to baseline, failing, and restored logs
and records hashes before and after. This demonstrates detection of one known
bug; it is not a claim that every possible bug has been ruled out. The final
submitted artifact is the restored, unmodified model output.

## Regenerate with local Qwen

Regeneration is optional and changes the saved artifacts. It needs an existing
Ollama installation and the already-installed `qwen2.5:3b` model. The project
does not download a model, contact a cloud API, or start inference on import.

On Windows, close any separately running Ollama service yourself before using:

```powershell
py -3.10 run_local_pipeline.py --allow-model --stage testing
```

The helper refuses to start if another model process/listener exists or less
than 4.5 GiB RAM is available. It starts a private local service, runs the three
real-agent smoke scripts sequentially with `num_gpu=0` and `num_thread=2`, unloads the
model between calls, and closes its own service on completion or failure.
There are no automatic model retries. `evidence/local_run.json` records the
outcome and cleanup checks; the machine-specific service log stays local.
To explicitly regenerate only the Developer from an existing accepted plan,
use `--stage developer` instead of `--stage testing`. A failed stage is never retried automatically.

The `test_analyst.py`, `test_planner.py` and `test_developer.py` scripts reuse the
normal stage runners. Each requires `--allow-model` and an already-running
local service when invoked individually. Prefer the managed helper above.
It saves each test's displayed output under `evidence/smoke/`. If requirements
are regenerated, both downstream stages must be regenerated too. Run the offline
checks and the deliberate-bug exercise after any new model generation.

## Project files and source material

- `analyst_agent.py`, `planner_agent.py`, `developer_agent.py`: prompts, model calls, and validation.
- `run_analyst.py`, `run_planner.py`, `run_developer.py`: load and save each stage's artifact.
- `artifacts/`: requirements, accepted plan and the PDF-requested code mirror.
- `generated/navigation_logic.py`: accepted Developer output, not a handwritten test fixture.
- `test_analyst.py`, `test_planner.py`, `test_developer.py`: opt-in real-agent tests.
- `test_generated_navigation_logic.py`: exhaustive and focused behavior tests.
- `run_bug_demo.py`: reproducible failing/restored test evidence.
- `local_qwen.py`, `workspace_io.py`: local HTTP transport and complete-file writes.
- `inspect_results.py`, `try_navigation.py`: offline verification and a small decision example.
- `tests/`: synthetic, offline regression cases; these never count as real model results.
- `evidence/`: original exchanges, local-run metadata, and the navigation verification report.

The source revisions and preserved input identities are listed in
`evidence/source_materials.json`. The teacher's Plan and Develop and Testing
PDFs are included unchanged. The Testing starter was cloned from
[the teacher's repository](https://github.com/prabhatram/scse-26-project-testing)
and its history merged into this group's existing repository. Its sample was
expanded rather than treated as a completed test suite.

The Testing assignment message sets September 25 at midnight; confirm the
course timezone in Moodle. One group member submits this existing repository:

[1Guchentao/scse_agentic_se_naming-is-hard](https://github.com/1Guchentao/scse_agentic_se_naming-is-hard)

The previous Analyst implementation contained a cloud credential. Current
source removes it and uses local Qwen. The owner still needs to revoke that
credential because deleting it from current files does not remove exposure
from earlier Git history. No previously exposed credential is used here.
