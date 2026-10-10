# Recorded Routes and Results

The completed run is [20261010T142530Z](../evidence/integration/20261010T142530Z/),
recorded on 10 October 2026. It contains an initial round and a revised round,
each with six fresh Qwen calls, generated tests, logical simulation, four
IR-SIM routes and both reviews. The [execution log](../evidence/integration/20261010T142530Z/trace.log)
shows the order and timestamps.

## Watch the revised routes

| Map | Initial steps | Revised steps | Goal reached | View |
| --- | ---: | ---: | --- | --- |
| Easy | 150 | 150 | Yes | [Animation](../evidence/integration/20261010T142530Z/revision/worlds/world_easy/route.gif), [image](../evidence/integration/20261010T142530Z/revision/worlds/world_easy/route.png) |
| Medium | 148 | 148 | Yes | [Animation](../evidence/integration/20261010T142530Z/revision/worlds/world_medium/route.gif), [image](../evidence/integration/20261010T142530Z/revision/worlds/world_medium/route.png) |
| Hard | 187 | 187 | Yes | [Animation](../evidence/integration/20261010T142530Z/revision/worlds/world_hard/route.gif), [image](../evidence/integration/20261010T142530Z/revision/worlds/world_hard/route.png) |
| Custom | 193 | 193 | Yes | [Animation](../evidence/integration/20261010T142530Z/revision/worlds/world_custom/route.gif), [image](../evidence/integration/20261010T142530Z/revision/worlds/world_custom/route.png) |

All four maps reached the goal without a recorded collision in both rounds.
Average steps were 169.5, with every route within the 200-step efficiency
threshold. The overall limit was 300 steps. Each map folder includes the
teacher's original report, measured poses, console output and exact input code.
The PDF calls the third map difficult; the supplied file is `world_hard.yaml`.

The figures retain the simulator's Running title. The teacher script ends
when the robot is within 0.4 units of its goal, before the simulator necessarily
changes that title. Goal arrival was also checked against the recorded pose.

## Tests and revision

Each round passed all 64 generated pytest cases and all 64 independently
checked sensor combinations. Swapping LEFT and RIGHT in a separate control
caused 31 assertion failures, confirming that the tests detect that error.
Those expected failures are not failures of the submitted navigation code.

The revised adapter flattens the nested goal conditions and uses a
`blocked_paths` lookup while keeping the original `navigate` helper. The
navigation policy did not change, so equal route lengths are expected. This
is a readability revision, not an improvement in measured route speed.

The supporting offline suite passed 123 tests; the previous stages still
passed all 108 regression tests. The saved-evidence verifier also passed,
including source hashes, model handoffs, executed code, state coverage and
published reports. All eight animations had multiple changing frames, and
their eight route images were checked for nonblank output.

## Inspect the evidence

- [Initial round](../evidence/integration/20261010T142530Z/initial/)
- [Revised round](../evidence/integration/20261010T142530Z/revision/)
- [Final logical simulation](../artifacts/simulation_report.json) and [review](../artifacts/simulation_review.json)
- [Final test report](../artifacts/test_report.json)
- [Final benchmark](../artifacts/irsim_benchmark_report.json) and [review](../artifacts/benchmark_review.json)
- [Model-service cleanup](../evidence/integration/20261010T142530Z/runtime/cleanup.json)

The recorded maximum GPU temperature was 78 C and the lowest sampled
available RAM was 4.04 GiB. No protection limit was crossed in this completed
run; the temporary service stopped and its port closed. Preliminary and
interrupted development runs remain in a local archive outside the repository,
not mixed into these accepted results.

These measurements cover the defined boolean inputs and the four supplied
maps, not every possible map or a physical robot. Rechecking the saved work
does not need a model download; see the [local commands](../README.md#run-locally).
