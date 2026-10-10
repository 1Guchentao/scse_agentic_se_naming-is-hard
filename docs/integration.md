# Integration Notes

The integration entrypoint is `main.py`. It loads `brief.txt` and uses the
group's existing Analyst, Planner and Developer. Their original CPU transport
is temporarily replaced within this invocation by a private GPU session.
The earlier files and their stand-alone behavior are not rewritten.

## What happens in a round

The Analyst produces requirements and the Planner builds the two-case policy.
The Developer produces the complete navigation module in the initial round.
The Test Agent receives the brief, requirements, plan and that exact module,
then returns a pytest file. Eight obstacle patterns crossed with eight goal
patterns cover the full 64-state input domain.

The generated tests run in a separate workspace. Calls to the public
function are recorded to check actual state coverage, not just the number of
collected tests. They also run against a control that swaps LEFT and RIGHT.
This control is kept separate from the accepted code. It must produce
assertion failures, not import errors or skipped tests.

The logical runner uses its own clear-exit table and saves each expected and
actual action. Its reviewer receives the summary and any failed cases. Next,
the benchmark launches the unchanged teacher script once for each map.
A second reviewer receives the world measurements and deterministic quality
flags. Models may explain the results but cannot override measured failures.

## Revision

The revision request contains the preceding code, both reviews, the benchmark,
requirements and plan. The model returns a new public adapter; the application
joins it to the preserved original helper and validates the complete module.
The original reply and assembled source are both retained.

The new adapter replaces nested goal checks with flat combined conditions
and uses `blocked_paths` for its local direction map. All returns still call
the preserved `navigate` helper.
When the original measurements already pass, this is a readability revision,
not a claimed repair of a fault. The revised round still runs the Analyst,
Planner, Test Agent, logical runner, both reviewers and all four worlds again.
No earlier model replies or route measurements are substituted for those calls.

## Simulation evidence

The teacher program controls actions, velocities, turn locking, obstacles,
goal tolerance and step limits. `integration/capture.py` observes its real
steps and saves frames before the environment closes. It disables interactive
display for batch work but does not change the navigation or physics.

Each workspace includes the exact teacher script, selected policy and map,
the original report and console output, a pose record, and route PNG/GIF.
Goal completion is checked against the measured final position and the
teacher's 0.4-unit tolerance. The hard limit is 300 steps; an efficient goal
arrival takes at most 200.

The plot retains IR-SIM's own status title, which can still say Running when
the teacher's separate 0.4-unit arrival check stops the loop. The final pose
and the teacher report, rather than that title alone, determine goal arrival.

All four worlds remain in the benchmark denominator, including failures.
If a process fails before reporting its step count, the average is marked
unavailable rather than inventing that count. Safety also checks recorded
collision flags, since termination alone does not always imply a collision.

## Machine safeguards

The GPU entrypoint requires 4.5 GiB of available RAM and 4500 MiB of free GPU
memory before starting. It waits for cooling between requests at 65 C or more
and stops if RAM falls below 1.25 GiB or GPU temperature reaches 80 C.
These limits reduce load; they cannot guarantee hardware stability.
Requests use batches of 64 tokens to reduce peak GPU load. The 80 C stop
threshold is not raised when a run is interrupted by temperature protection.

Vulkan mode hides CUDA from the temporary Ollama process to avoid the local
CUDA kernel compatibility error. It selects the requested Vulkan device and
checks that the model was actually loaded on GPU. Only the service started
by this run and its child processes are closed. Other applications are not
terminated. A model is unloaded after each response; failures are recorded,
with no automatic retry loop.

## Checking a saved run

`verify_integration.py` checks source identities, the unchanged teacher files,
every model request and response, agent handoffs, executed pytest copies,
JUnit results, observed input coverage, both simulations and published files.
It also checks the prior 108-test regression log and the service cleanup record.

The run folder is an inspectable record, not an independent attestation service.
Results are limited to the stated six-boolean interface and the four supplied
maps. They do not establish correctness for all environments or a physical
robot. The saved earlier-stage evidence is separate and remains checkable
through `inspect_results.py`.

[Return to the project overview](../README.md)
