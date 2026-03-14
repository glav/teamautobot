# Implementation Plan: First Planner and Task-Graph Slice

**Status**: Implemented - initial planner slice landed; retained as the repo-tracked plan record

**Related docs**:

- `README.md`
- `AGENTS.md`
- `docs/teamautobot-design.md`
- `docs/decision-records/2026-03-12-custom-agent-runtime.md`
- `docs/decision-records/2026-03-12-llm-interface-strategy.md`

## Goal

Add the first repo-owned planner slice that can model a small task graph, execute it deterministically through the existing runtime, persist planner and run artifacts, and expose the flow through a CLI-verifiable harness.

**This plan was reviewed and approved before implementation and is retained as the repo-tracked implementation record for this slice.**

## Problem statement

TeamAutobot now has a working foundation slice for single-task execution:

- a repo-owned single-task agent loop,
- JSONL-backed event logging,
- JSON artifact persistence,
- a deterministic demo harness,
- a TeamAutobot-owned LLM interface, and
- one validated concrete provider adapter.

What is still missing is the layer that turns an objective into coordinated work. The next milestone should close that gap without prematurely taking on dynamic replanning, multi-agent negotiation, long-lived agent processes, replay/resume, or a full context store.

## Why this is the next milestone

- `docs/teamautobot-design.md` defines the Goal Planner as the component that decomposes objectives into a task graph, assigns work, and replans adaptively.
- `AGENTS.md` already reserves `src/teamautobot/planner/` as part of the intended package shape.
- The current code already provides the execution, event, artifact, CLI, and LLM seams needed to support a narrow planner slice.
- Accepted ADRs for D1 and D2 mean the next step should stay repo-owned and work behind stable internal interfaces rather than adopting an external framework.

## Research summary

### Current repo baseline

- `src/teamautobot/agents.py` contains `SingleTaskAgent`, which already emits task and artifact events, performs tool calls, and persists task artifacts.
- `src/teamautobot/events.py` contains an in-process `EventBus` backed by `JsonlEventStore`, which matches the current D3 direction well enough for a first planner slice.
- `src/teamautobot/artifacts.py` provides a simple JSON artifact persistence primitive that should be reused instead of replaced.
- `src/teamautobot/tools.py` already provides a small tool registry abstraction that the planner runtime can continue to rely on via the existing agent execution path.
- `src/teamautobot/demo.py` and `src/teamautobot/cli.py` already establish the current harness pattern: deterministic demo runs that persist outputs to disk and return machine-readable JSON.
- `tests/test_cli.py` and `tests/test_azure_openai.py` show the current testing style and confirm the repo already values deterministic, local verification.
- Baseline validation was re-run before drafting this plan with `uv run pytest -q`, and the current suite passed.

### Relevant design and ADR constraints

- D1 is accepted: TeamAutobot owns its runtime boundaries and should keep orchestration semantics in-repo.
- D2 is accepted: TeamAutobot owns its LLM interface and should add behavior behind repo-owned adapters, not around them.
- D3 is still open, but the design currently leans toward in-process event transport with JSONL persistence.
- D4 is still open, so the planner slice should not commit the repo to FTS, vector search, or a final context topology.
- D5 is still open, so the planner slice should not require long-lived agents or pooled workers.
- D7 is still open, so deterministic, fake-driven tests must be treated as part of the milestone rather than an afterthought.

## Recommended milestone boundary

### In scope

- Add a new `src/teamautobot/planner/` package with typed planner and task-graph models.
- Define validation rules for planner-owned task graphs, including dependency integrity and deterministic ready-task selection.
- Implement a static planner that turns a built-in scenario into a small task graph.
- Implement a dependency-aware execution coordinator that runs tasks in deterministic serial order through the existing single-task runtime.
- Treat assignee and persona data as planner metadata only for this milestone.
- Persist a plan snapshot before execution and an execution summary after execution.
- Add planner-visible event coverage for assignment, blocking, failure, and overall completion while reusing the existing event infrastructure.
- Add a CLI-verifiable planner demo command that produces JSON output and durable on-disk artifacts.
- Add deterministic tests for models, validation, execution, failure handling, and the CLI harness.

### Explicitly out of scope

- Adaptive replanning after task completion
- Parallel task execution
- Agent-to-agent messaging and negotiation
- Review workflow semantics
- Long-lived agent processes or agent pools
- Cross-run memory and general context retrieval
- FTS5 or vector indexing
- Replay and resume from arbitrary checkpoints
- Dashboard or intervention UI
- General objective markdown parsing beyond what the small planner demo requires

## Decision handling for this milestone

### D3 event transport assumption

Use the existing in-process `EventBus` and JSONL persistence model as the execution transport for the planner slice. This is enough to make the planner observable and testable without forcing the repo into brokers, subscriptions, or external services.

This milestone assumption is not intended to lock TeamAutobot into in-process transport permanently. The event model and runtime boundaries should remain capable of evolving to an out-of-process transport in the future, including transport across separate processes or machines, if that later proves to be a worthwhile architectural addition.

### D5 execution assumption

Treat execution as spawn-per-task semantics behind a small internal seam. The planner may assign a logical persona or agent identity to a task, but that assignment is metadata only in this milestone. The runtime should not depend on long-lived resident agent processes, pooled workers, or persona-specific executors. This keeps the slice future-safe while D5 remains open.

### D4 context and dependency handoff assumption

Defer the real context-store decision. For this milestone, downstream tasks receive only a minimal dependency handoff payload containing:

- a list of per-dependency handoff objects
- each object contains `task_id`, `artifact_path`, and `summary`
- each `summary` value is a tiny planner-produced string derived deterministically from the upstream task artifact, preferably from top-level `assistant_text` when present
- each `summary` value is normalized to a single line and capped at a small fixed size such as 200 characters

Failed or blocked upstream tasks do not produce dependency handoff objects. If a required upstream task fails or is blocked, dependent tasks are marked `blocked` and do not execute in this milestone.

No broader retrieval, search, semantic context assembly, or cross-run memory behavior is part of this slice.

### D7 testing assumption

Use deterministic fake or scripted execution paths and stable ordering rules so the planner slice can be verified locally and in CI without network calls or timing-sensitive behavior.

## Frozen milestone contract

- **Input contract**: the first planner command supports a built-in scenario only. It does not yet accept general objective files or an arbitrary structured planner input format.
- **Execution contract**: the runner is dependency-aware but serial. When multiple tasks are ready, it executes them by ascending persisted `order_index`.
- **Assignee contract**: task assignee or persona fields are metadata only. They do not select different runtime implementations in this milestone.
- **Dependency handoff contract**: downstream tasks receive only dependency artifact references plus a short summary list prepared by the planner runtime.
- **Persistence contract**: the planner demo follows the existing per-run directory pattern and persists planner-owned JSON artifacts through the existing `ArtifactStore`.
- **Verification contract**: the CLI and event log are both treated as stable verification surfaces and must therefore have explicit schemas.

## Proposed architecture slice

### New package shape

```text
src/teamautobot/planner/
├── __init__.py
├── models.py
├── interfaces.py
├── validation.py
├── static_planner.py
├── runtime.py
└── demo.py
```

### Existing modules to extend, not replace

- `src/teamautobot/agents.py` should remain the leaf task executor for now. If needed, add a thin adapter rather than moving planner logic into the agent implementation.
- `src/teamautobot/events.py` should remain the event transport boundary. Any additions should be small and additive, such as helper readers or a few planner-visible event shapes.
- `src/teamautobot/artifacts.py` should remain the persistence primitive. If planner-specific helpers are needed, add them without replacing the base store.
- `src/teamautobot/cli.py` should remain the main CLI entry point and gain a planner-focused command rather than introducing a second top-level CLI.
- `src/teamautobot/demo.py` should remain the current single-agent demo. Planner-specific scenarios can live alongside it in `src/teamautobot/planner/demo.py`.

### Proposed responsibilities

- `models.py` defines planner-owned task, graph, status, assignment, snapshot, and execution-summary types.
- `interfaces.py` defines narrow seams such as a planner interface and a task-executor interface so the implementation does not hardcode future agent persistence decisions.
- `validation.py` owns graph integrity checks such as duplicate IDs, missing dependencies, cycles, and deterministic ready-set rules, including persisted `order_index` values.
- `static_planner.py` creates a small, explicit task graph from the built-in scenario only.
- `runtime.py` owns dependency-aware scheduling, execution order, task status transitions, planner-visible event emission, and summary persistence.
- `demo.py` provides a deterministic built-in scenario and a simple wiring path for CLI and tests.

## Planner run layout

Planner demo runs should follow the same per-run directory pattern already used by the existing demo flow, with a dedicated default base directory such as `.teamautobot/planner-runs/`.

Recommended per-run layout:

```text
<run_dir>/
├── events.jsonl
└── artifacts/
    ├── planner/
    │   ├── plan.json
    │   └── execution-summary.json
    └── tasks/
        ├── capture-objective.json
        ├── draft-work-breakdown.json
        ├── draft-validation-checklist.json
        └── publish-summary.json
```

For this milestone:

- planner-owned artifacts should live under `run_dir / "artifacts/planner"`
- task-owned artifacts should live under `run_dir / "artifacts/tasks"`
- the implementation may use separate `ArtifactStore` instances rooted at those directories
- `JsonlEventStore(run_dir / "events.jsonl")` should continue to back the event log.
- `plan.json` and `execution-summary.json` should include `schema_version: 1`
- CLI output should point directly to `run_dir`, `plan_path`, `summary_path`, `event_log_path`, and the list of task artifact paths.

## Minimal event contract

The planner slice should keep event additions small and explicit.

Required event types for this milestone:

- `task.assigned`
- `task.started`
- `tool.called`
- `tool.completed`
- `artifact.created`
- `task.completed`
- `task.failed`
- `task.blocked`
- `system.error`
- `system.complete`

Required event conventions:

- `source` is `"planner"` for planner-originated events and the executing agent ID for task/tool events emitted by the existing runtime.
- `target` is the logical assignee for `task.assigned` and `null` for all other events in this milestone unless the existing runtime already populates it.
- `correlation_id` is the task ID for task-scoped events and the run ID for `system.complete`.
- `payload` should include at minimum:
  - task-scoped events: `task_id`
  - `task.assigned`: `task_id`, `assignee`, `dependencies`
  - `task.started`: `task_id`
  - `tool.called`: `task_id`, `tool_call_id`, `tool_name`, `arguments`
  - `tool.completed`: `task_id`, `tool_name`, `output`
  - `artifact.created`: `task_id`, `artifact_path`
  - `task.completed`: `task_id`, `artifact_path`
  - `task.blocked`: `task_id`, `blocked_by`
  - `task.failed`: `task_id`, `message`
  - `system.error`: `kind`, `message`, and, if the existing runtime is adjusted during implementation, `task_id`
  - `system.complete`: `run_id`, `completed_task_ids`, `failed_task_ids`, `blocked_task_ids`

## CLI JSON contract

The first planner command should be `teamautobot planner demo --json`.

Allowed `status` values:

- success: `ok`
- failure: `error`

Success payload:

- `schema_version`
- `status`
- `scenario_name`
- `run_dir`
- `plan_path`
- `summary_path`
- `event_log_path`
- `artifact_paths`
- `completed_task_ids`
- `failed_task_ids`
- `blocked_task_ids`

Failure payload:

- `schema_version`
- `status`
- `scenario_name`
- `run_dir`
- `plan_path`
- `summary_path`
- `event_log_path`
- `failed_task_ids`
- `blocked_task_ids`
- `message`

Failure behavior:

- exit with a non-zero status code
- still persist the event log
- still persist the plan artifact
- persist an execution summary that records success, failure, and blocked counts

## Proposed planner demo scenario

Use a small static DAG with one branch but keep execution serial for this milestone:

- `capture-objective`
- `draft-work-breakdown`, depends on `capture-objective`
- `draft-validation-checklist`, depends on `capture-objective`
- `publish-summary`, depends on both upstream tasks

This proves task-graph modeling, dependency handling, future parallel-readiness, and planner artifact persistence without requiring unresolved multi-agent behavior.

## Planned work breakdown

### Phase 1: Planner domain contracts

**Objective**: Introduce repo-owned planner and task-graph primitives without committing to adaptive planning or a final persistence topology.

**Planned work**

- Add typed planner models for task nodes, task status, assignments, graph state, plan snapshots, and execution summaries.
- Add graph validation rules for duplicate task IDs, missing dependency references, cycle detection, and deterministic ready-task ordering based on persisted `order_index`.
- Add serialization helpers or conventions for stable planner-owned JSON artifacts.
- Define narrow planner and task-executor interfaces so later lifecycle changes stay behind replaceable seams.

**Likely files**

- `src/teamautobot/planner/__init__.py`
- `src/teamautobot/planner/models.py`
- `src/teamautobot/planner/interfaces.py`
- `src/teamautobot/planner/validation.py`

**Validation**

- Add tests for model defaults and serialization behavior.
- Add tests for graph validation and deterministic ready-task selection.
- Add tests that prove `order_index` is persisted and used as the canonical ready-task tie-break rule.

**Phase acceptance**

- Planner models exist under `src/teamautobot/planner/`.
- Invalid graphs are rejected with explicit errors.
- Graph state can be serialized to stable JSON for artifact persistence.
- The task graph persists deterministic `order_index` values used by the runtime and tests.

### Phase 2: Static planner and dependency-aware runtime

**Objective**: Implement the smallest execution-capable planner slice: a static DAG and a deterministic serial runner that uses the existing runtime instead of replacing it.

**Planned work**

- Implement a static planner that returns the built-in scenario graph only.
- Implement a dependency-aware runner that executes only ready tasks and records status transitions.
- Add an adapter layer from planner tasks to the existing `AgentTask` execution path.
- Add the minimal dependency handoff payload for downstream tasks: artifact references plus short summaries from completed prerequisite tasks.
- Persist a plan snapshot before execution and a run summary after execution.
- Emit the minimal planner-visible event set and payloads defined in this plan.
- Preserve or enrich existing `system.error` events from the current runtime so failure traces remain visible in the event log.

**Likely files**

- `src/teamautobot/planner/static_planner.py`
- `src/teamautobot/planner/runtime.py`
- Optional small additive changes to `src/teamautobot/events.py`
- Optional small additive changes to `src/teamautobot/artifacts.py`

**Validation**

- Add tests that prove tasks execute only after dependencies are satisfied.
- Add failure-path tests that prove downstream tasks are blocked if a prerequisite fails.
- Add artifact assertions for the plan snapshot and execution summary.

**Phase acceptance**

- A static graph can be planned and executed end to end.
- Dependency ordering is deterministic and test-covered.
- The runner reuses existing runtime pieces instead of introducing a replacement execution path.

### Phase 3: CLI-verifiable planner demo

**Objective**: Expose the planner slice through a narrow CLI harness that is easy to inspect and easy to test.

**Planned work**

- Add a planner-focused nested CLI command, `teamautobot planner demo --json`, aligned with the repo's existing subcommand patterns.
- Add a deterministic built-in planner scenario with at least one branch in the graph.
- Return the exact machine-readable JSON payload defined in this plan for both success and failure paths.
- Keep the CLI surface intentionally narrow and demo-oriented until the planner contract is stable.

**Likely files**

- `src/teamautobot/planner/demo.py`
- `src/teamautobot/cli.py`
- `README.md` only after implementation is approved and the command exists

**Validation**

- Add CLI tests that verify success output, file creation, and stable JSON structure.
- Ensure failure paths return a non-zero exit code with structured JSON output.

**Phase acceptance**

- The planner demo command exists and is covered by tests.
- The command demonstrates a real DAG rather than a linear task list.
- The output is stable enough for both humans and tests to verify.

### Phase 4: Deterministic hardening for future replay and multi-agent work

**Objective**: Make the first planner slice durable enough for CI and deterministic verification without expanding scope into replay or multi-agent behavior.

**Planned work**

- Add test helpers or injected seams for normalizing timestamps, UUIDs, or run IDs where needed.
- Add any small event-log reader helpers that materially improve testability.
- Assert normalized planner semantics rather than relying on unstable incidental values.
- Verify the explicit event, artifact, and CLI contracts defined in this plan.

**Likely files**

- New or updated planner-focused tests under `tests/`
- Optional small helper additions to `src/teamautobot/events.py`

**Validation**

- Re-run the full test suite with `uv run pytest`.
- Run existing lint and formatting checks that the repo already documents after code changes are in place.

**Phase acceptance**

- Planner semantics are deterministic under scripted or fake execution.
- The new test coverage includes both happy-path and failure-path behavior.
- The slice is stable enough to extend without immediate refactoring.

## Validation strategy

### Unit coverage

- Planner model defaults
- Graph validation rules
- Deterministic ready-task selection
- Persisted `order_index` values
- Status transitions
- Serialization behavior

### Integration coverage

- Static plan creation
- Dependency-aware execution through the current runtime
- Dependency handoff payload shape
- Plan snapshot persistence
- Execution summary persistence
- Event-log contents and ordering
- Preservation of failure traces via `task.failed` and `system.error`

### CLI coverage

- Planner demo success path
- Planner demo failure path
- Exact JSON payload keys and file existence
- Non-zero exit behavior on failure
- Presence of `schema_version` in planner-owned artifacts and CLI JSON

### Commands to use when implementation begins

- `uv run pytest`
- `uv sync --group dev`
- `uv run ruff check .`
- `uv run ruff format --check .`

## Risks and mitigations

### Risk: Scope creep into full multi-agent collaboration

**Mitigation**: Keep the milestone static, deterministic, and serial. Do not introduce agent messaging, review loops, or adaptive replanning in this slice.

### Risk: Coupling the planner too tightly to `SingleTaskAgent`

**Mitigation**: Add an internal execution seam so planner tasks can be translated into the existing runtime path without embedding planner semantics inside the agent implementation.

### Risk: Event schema churn

**Mitigation**: Keep event additions minimal and aligned with the event categories already defined in the design specification. Prefer richer artifact payloads over a large new event vocabulary, but preserve existing runtime failure signals such as `system.error`.

### Risk: Execution order changes during serialization or refactoring

**Mitigation**: Persist explicit `order_index` values in the task graph and use them as the canonical ready-task tie-break rule in both runtime code and tests.

### Risk: Hidden commitment on D5

**Mitigation**: Use logical assignees and a narrow task-executor boundary. Avoid APIs that require long-lived agents, pools, or background workers.

### Risk: Non-deterministic tests

**Mitigation**: Use scripted or fake execution paths, stable ordering rules, and controlled assertions around timestamps and IDs.

### Risk: Premature expansion into objective parsing or context retrieval

**Mitigation**: Use a built-in scenario only and defer richer objective parsing and context retrieval until the planner slice is proven.

## Implementation-ready acceptance criteria

- A new `src/teamautobot/planner/` package exists with typed task-graph models and validation.
- A static planner can produce the built-in scenario DAG and no broader planner input mode is introduced in this milestone.
- A dependency-aware runner can execute that DAG serially through the existing runtime.
- The task graph persists explicit `order_index` values and the runner uses them as the deterministic execution tie-break rule.
- Task assignee or persona data remains metadata only and does not introduce persona-specific executors.
- Downstream tasks receive only dependency artifact references plus short prerequisite summaries derived deterministically from upstream artifacts.
- Planner runs persist a versioned plan snapshot, versioned execution summary, task artifacts, and a JSONL event log under the defined per-run layout.
- The CLI exposes the planner slice with the exact success and failure JSON contracts defined in this plan, including `schema_version`.
- Failure runs record failed and blocked tasks, preserve the event log, and return a non-zero exit code.
- Deterministic tests cover graph validation, scheduling, failure handling, artifacts, event payloads, failure traces, and the CLI harness.
- The implementation does not require dynamic replanning, long-lived agents, or context retrieval.

## Review confirmations before implementation

- Confirm the first planner command is built-in-scenario only.
- Confirm task assignee and persona remain metadata only in this milestone.
- Confirm dependency handoff is limited to artifact references plus short summaries.
- Confirm the per-run artifact layout and CLI JSON contract are acceptable.
- Confirm `order_index` is the canonical deterministic ready-task ordering rule.

## Owner approval checklist

- [ ] The milestone should stay limited to a static, deterministic planner slice.
- [ ] Multi-agent collaboration, review loops, and adaptive replanning stay out of scope.
- [ ] The first runner should be dependency-aware but serial.
- [ ] The first planner command should support the built-in scenario only.
- [ ] Task assignee and persona should remain metadata only in this milestone.
- [ ] Downstream task handoff should be limited to artifact references plus short summaries.
- [ ] The planner should live under `src/teamautobot/planner/` and extend existing runtime pieces rather than replace them.
- [ ] The planner demo should use the defined per-run artifact layout, versioned planner-owned outputs, and JSON-verifiable CLI contract.
- [ ] The task graph should persist `order_index` for deterministic execution and testing.
- [ ] Deterministic tests are required before the milestone is considered complete.
