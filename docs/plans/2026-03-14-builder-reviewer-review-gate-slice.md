# Implementation Plan: Builder-Reviewer Review-Gate Slice

**Status**: Implemented - initial review-gate slice landed; retained as the repo-tracked plan record

**Related docs**:

- `README.md`
- `AGENTS.md`
- `docs/teamautobot-design.md`
- `docs/plans/2026-03-13-first-planner-task-graph-slice.md`
- `docs/decision-records/2026-03-12-custom-agent-runtime.md`
- `docs/decision-records/2026-03-12-llm-interface-strategy.md`

## Goal

Add the first TeamAutobot collaboration slice in which a builder and reviewer can collaborate on a task through an explicit review gate, using the existing planner runtime, event bus, and artifact model without yet taking on dynamic replanning or a full revision loop.

**This plan was reviewed and approved before implementation and is retained as the repo-tracked implementation record for this slice.**

## Problem statement

The first planner slice is now implemented. TeamAutobot can model a small task graph, execute it deterministically in serial order, persist a plan and execution summary, and expose the flow through a CLI-verifiable demo. What it still cannot do is demonstrate actual collaboration between specialized agents.

The next milestone should close that gap by proving a minimal builder-reviewer collaboration path:

- builder produces an implementation-style artifact,
- reviewer evaluates it through a review gate,
- review events are persisted on the event bus,
- approval or rejection affects downstream execution,
- the full flow remains deterministic and harnessable.

This should stay intentionally smaller than a full review-feedback-revise-re-review loop.

## Why this is the next milestone

- `docs/teamautobot-design.md` Phase 2 calls for multi-agent collaboration, agent-to-agent communication via the event bus, and a review workflow.
- The next milestone in the design roadmap is: “Two agents (builder + reviewer) can collaborate on a task.”
- The current planner runtime already provides:
  - typed task graphs,
  - deterministic scheduling,
  - JSONL event persistence,
  - per-run artifact layouts,
  - CLI verification surfaces,
  - deterministic demo/test doubles.
- The current planner slice intentionally left collaboration, review events, and persona-specific execution behavior out of scope, so those are now the clearest remaining gaps.

## Research summary

### Current repo baseline

- `src/teamautobot/planner/runtime.py` provides a deterministic serial scheduler with plan snapshots, execution summaries, blocked-task behavior, and task-level handoff payloads.
- `src/teamautobot/planner/demo.py` provides the current built-in planner demo with deterministic scripted execution and TeamAutobot-aligned runtime output paths.
- `src/teamautobot/agents.py` already supports structured task context and emits task/tool/artifact/system events through the shared `EventBus`.
- `src/teamautobot/events.py` already provides a persistent JSONL-backed event transport suitable for adding collaboration and review events.
- `tests/test_planner.py` and `tests/test_cli.py` already prove the repository can validate planner/runtime behavior deterministically without live provider calls.

### Relevant design constraints

- Phase 2 in `docs/teamautobot-design.md` calls for:
  - goal planner usage,
  - agent-to-agent communication via event bus,
  - review workflow,
  - a builder + reviewer milestone.
- The event model already reserves:
  - `agent.*` for direct agent communication,
  - `review.*` for review workflow,
  - `system.*` for runtime/system signaling.
- D1 remains accepted: TeamAutobot owns the runtime and orchestration semantics.
- D2 remains accepted: TeamAutobot owns the LLM client boundary.
- D3 still leans toward in-process + JSONL transport for now.
- D4 remains open, so the collaboration slice should still avoid a full context retrieval system.
- D5 remains open, so the collaboration slice should still avoid long-lived agents and pools.
- D7 remains open, so collaboration behavior must still be deterministic and CI-friendly.

## Recommended milestone boundary

### In scope

- Add the first builder-reviewer collaboration scenario to the planner runtime.
- Introduce persona-aware execution behavior for builder and reviewer demo tasks while keeping execution behind repo-owned interfaces.
- Add machine-readable review outputs so the runtime can respond to reviewer approval or rejection without parsing unstructured prose.
- Add explicit `review.*` events:
  - `review.requested`
  - `review.feedback`
  - `review.approved`
  - `review.rejected`
- Gate downstream execution on the reviewer outcome.
- Add a CLI-verifiable collaboration demo command under the planner CLI namespace.
- Add deterministic tests for approved and rejected review paths.

### Explicitly out of scope

- Dynamic replanning
- Arbitrary objective-file planning
- Multi-reviewer orchestration
- General `agent.question` / `agent.answer` messaging
- Full revision / re-review cycle
- Parallel execution
- Long-lived agent processes or agent pools
- Resume/replay implementation
- Context retrieval/search
- Dashboard or intervention UI

## Frozen milestone contract

- **Input contract**: the collaboration slice uses a built-in review-gate scenario only.
- **Execution contract**: the runner remains serial and dependency-aware.
- **Persona contract**: this milestone introduces actual builder and reviewer execution behavior for demo tasks; other personas remain out of scope.
- **Review input contract**: `review-slice` reuses the existing `dependency_handoffs` mechanism only. In this slice it must receive exactly one upstream handoff, from `implement-slice`, and that handoff is the sole review subject reference.
- **Review contract**: reviewer output must include a machine-readable result with required `subject_task_id`, `decision`, `summary`, and `feedback_items`, not only freeform assistant text. `subject_task_id` must equal the single upstream handoff task ID.
- **Outcome contract**: reviewer approval allows the run to proceed. Reviewer rejection is treated as a completed review outcome, not a task execution failure: `review-slice` completes with `decision=rejected`, downstream publish/finalization tasks become blocked, and overall CLI run status is `error`.
- **Persistence contract**: the collaboration slice reuses the existing TeamAutobot per-run artifact/event layout and extends it with structured review output and a persisted review artifact.
- **Verification contract**: exact approval and rejection CLI JSON payloads, review artifacts, and event-log contents are treated as stable verification surfaces.

## Milestone assumptions and decision handling

### D3 event transport assumption

Keep using the existing in-process `EventBus` plus JSONL persistence for this milestone. The collaboration slice should add new event categories and payloads, not a new transport layer.

### D5 execution assumption

Continue with spawn-per-task semantics behind internal execution interfaces. Collaboration is expressed through task sequencing and persisted events, not through long-lived in-memory agent sessions.

### D4 context assumption

Continue using explicit dependency handoffs and artifact references. Do not add generalized retrieval or semantic search yet.

### D7 testing assumption

Collaboration behavior must be demonstrable through deterministic fake/scripted agents, stable event sequences, and local CLI/test verification.

## Proposed architecture slice

### New and changed code areas

Likely additions or extensions:

```text
src/teamautobot/planner/
├── models.py              # extend for review verdict/result payloads
├── interfaces.py          # extend if executor outputs need structured result data
├── runtime.py             # add review-gate semantics and review event emission
├── demo.py                # keep planner demo; add review-gate scenario/executor wiring
├── static_planner.py      # add the collaboration scenario graph
└── review.py              # optional home for review verdict/result helpers
```

### Existing modules to extend, not replace

- `src/teamautobot/agents.py` should remain the leaf task executor boundary.
- `src/teamautobot/events.py` should remain the transport boundary.
- `src/teamautobot/artifacts.py` should remain the artifact persistence primitive.
- `src/teamautobot/cli.py` should gain another narrow planner subcommand rather than a separate top-level CLI.

### Proposed new runtime seam

The current `TaskExecutionOutput` is sufficient for task completion bookkeeping, but not for review-gate semantics. This milestone should add a structured result field or equivalent machine-readable contract so the runtime can consume:

- review verdict (`approved` / `rejected`)
- feedback items or summary
- required subject-task identifier derived from the single upstream dependency handoff

This should be repo-owned and generic enough to support future gated task types without tying the runtime to one hard-coded review implementation.

## Review input and subject contract

- `review-slice` should reuse the existing `dependency_handoffs` path as its only review-input mechanism.
- For this milestone, `review-slice` must have exactly one upstream dependency: `implement-slice`.
- The runtime should pass that handoff into the reviewer task context unchanged.
- `subject_task_id` is required on the structured review result and all `review.*` events, and it must equal `dependency_handoffs[0].task_id`.
- `subject_artifact_path` should be derived from `dependency_handoffs[0].artifact_path`; this avoids creating a second review-subject plumbing path.

## Minimal review result contract

The collaboration slice should keep the review result intentionally small and machine-readable.

Recommended minimum fields:

- `subject_task_id`
- `decision` with allowed values `approved` or `rejected`
- `summary` as a one-line reviewer summary
- `feedback_items` as a list of small feedback objects, each with at least `message`

For this milestone:

- `subject_task_id` is required and must match the single upstream dependency handoff
- approved reviews may emit an empty `feedback_items` list
- rejected reviews should emit at least one feedback item
- the review task should still persist a normal task artifact; the structured review result is additional runtime data
- the runtime should consume the structured result directly rather than reparsing review artifacts

## Rejected review semantics

- `review-slice` is recorded as `completed` whenever the reviewer successfully returns a valid structured review result, including `decision=rejected`.
- `review-slice` is recorded as `failed` only when review execution itself fails, for example because of a runtime, tool, or model error and no valid review result is produced.
- A valid `decision=rejected` causes downstream finalization tasks such as `publish-summary` to become `blocked`.
- A pure review rejection leaves `failed_task_ids` empty; downstream blockage is expressed through `blocked_task_ids`.
- The CLI/reporting layer should surface a pure review rejection as overall `status=error` so batch and automation callers see the gate failure.

## Minimal review event contract

Required review events for this milestone:

- `review.requested`
- `review.feedback`
- `review.approved`
- `review.rejected`

Required semantics:

- `review.requested` is emitted by the planner runtime immediately before `review-slice` execution begins.
- `review.feedback` is emitted by the planner runtime immediately after `review-slice` completes and the runtime has consumed the structured review result.
- `review.approved` is emitted after `review.feedback` when `decision=approved`.
- `review.rejected` is emitted after `review.feedback` when `decision=rejected`.

Required correlation and routing conventions:

- all `review.*` events use `correlation_id=review_task_id`
- `review.requested`: source=`planner`, target=`reviewer`
- `review.feedback`: source=`reviewer`, target=`builder`
- `review.approved`: source=`reviewer`, target=`builder`
- `review.rejected`: source=`reviewer`, target=`builder`

Required minimum payloads:

- `review.requested`: `review_task_id`, `subject_task_id`, `subject_artifact_path`
- `review.feedback`: `review_task_id`, `subject_task_id`, `review_artifact_path`, `decision`, `feedback_items`
- `review.approved`: `review_task_id`, `subject_task_id`, `review_artifact_path`
- `review.rejected`: `review_task_id`, `subject_task_id`, `review_artifact_path`, `feedback_items`

Required minimal ordering:

- approval path: `review.requested` -> reviewer `task.started` -> zero or more `tool.*` events -> reviewer `artifact.created` -> reviewer `task.completed` -> `review.feedback` -> `review.approved`
- rejection path: `review.requested` -> reviewer `task.started` -> zero or more `tool.*` events -> reviewer `artifact.created` -> reviewer `task.completed` -> `review.feedback` -> `review.rejected` -> downstream `task.blocked`

The collaboration slice should preserve existing `task.*`, `artifact.*`, and `system.*` events in addition to these review events.

## Proposed collaboration demo scenario

Use a small static review-gate scenario:

- `capture-objective` (BA or PM-style setup task)
- `implement-slice` (builder)
- `review-slice` (reviewer), depends on `implement-slice`
- `publish-summary` (writer or planner-owned summary task), depends on `review-slice` approval

Deterministic behavior:

- in the approval path, `review-slice` emits approval events and `publish-summary` runs
- in the rejection path, `review-slice` emits rejection events and `publish-summary` becomes blocked

This proves real collaboration while avoiding revision/re-review complexity in the same milestone.

## Planned work breakdown

### Phase 1: Collaboration and review contracts

**Objective**: Define the minimal machine-readable contracts needed for a builder-reviewer review gate.

**Planned work**

- Extend planner/runtime models to represent review verdicts and structured task outputs.
- Define the review event payload contract.
- Implement the frozen single-handoff review subject contract.
- Keep the contract narrow enough to support only this review-gate slice.

**Likely files**

- `src/teamautobot/planner/models.py`
- `src/teamautobot/planner/interfaces.py`
- optional `src/teamautobot/planner/review.py`

**Validation**

- Unit tests for verdict/result models and serialization.
- Unit tests for review payload validation.

**Phase acceptance**

- Review outputs are machine-readable.
- The runtime can distinguish review approval from review rejection without scraping assistant prose.

### Phase 2: Builder-reviewer collaboration runtime

**Objective**: Teach the planner runtime to run a builder task followed by a reviewer task and react to the reviewer outcome.

**Planned work**

- Add the collaboration scenario graph.
- Add persona-aware demo executors for builder and reviewer.
- Emit `review.requested`, `review.feedback`, `review.approved`, and `review.rejected` events.
- Block downstream tasks when the reviewer rejects.
- Preserve the frozen review-event ordering and `correlation_id=review_task_id` semantics.
- Preserve task, review, artifact, and system failure traces in the event log.

**Likely files**

- `src/teamautobot/planner/runtime.py`
- `src/teamautobot/planner/static_planner.py`
- `src/teamautobot/planner/demo.py`

**Validation**

- Deterministic approval-path integration test
- Deterministic rejection-path integration test
- Event-log assertions for review events and blocked downstream tasks

**Phase acceptance**

- Builder and reviewer tasks both execute in the scenario.
- Review outcome changes downstream execution.
- Event log clearly shows the review workflow.

### Phase 3: CLI collaboration harness

**Objective**: Expose the collaboration slice through a narrow CLI demo surface.

**Planned work**

- Add a nested CLI command such as `teamautobot planner review-demo --json`.
- Return machine-readable JSON for both approval and rejection paths.
- Keep the current `planner demo` command intact.

**Exact CLI payload contract**

Approval path keys should be:

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
- `review_status`
- `review_task_id`
- `reviewed_task_id`
- `review_artifact_path`
- `feedback_count`

Required approval values:

- `status=ok`
- `review_status=approved`
- `failed_task_ids=[]`
- `blocked_task_ids=[]`
- `feedback_count=0`

Rejection path keys should be:

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
- `message`
- `review_status`
- `review_task_id`
- `reviewed_task_id`
- `review_artifact_path`
- `feedback_count`

Required rejection values:

- `status=error`
- `review_status=rejected`
- `review-slice` appears in `completed_task_ids`
- `failed_task_ids=[]` for pure review rejection
- downstream finalization task IDs appear in `blocked_task_ids`
- `review_artifact_path` appears in `artifact_paths`
- `feedback_count>=1`

Execution failures unrelated to a valid review verdict should continue to use the generic planner failure semantics rather than pretending a review decision exists.

**Likely files**

- `src/teamautobot/cli.py`
- `README.md`

**Validation**

- CLI success test for approved review path
- CLI failure test for rejected review path
- exact JSON key and value assertions for approval and rejection payloads

**Phase acceptance**

- Collaboration demo can be exercised entirely through CLI
- Output remains stable and machine-verifiable

### Phase 4: Deterministic hardening

**Objective**: Make the collaboration slice reliable enough for CI and future extension.

**Planned work**

- Normalize any unstable IDs/timestamps in test assertions where needed.
- Add regression tests for review event ordering and reviewer outcome handling.
- Keep collaboration behavior deterministic under scripted execution.

**Likely files**

- `tests/test_planner.py`
- `tests/test_cli.py`

**Validation**

- Re-run `uv run pytest`
- Re-run `uv run ruff check .`

**Phase acceptance**

- Collaboration behavior is deterministic and regression-tested.

## Validation strategy

### Unit coverage

- review verdict/result models
- review payload serialization
- blocked downstream behavior on rejection

### Integration coverage

- approved collaboration run
- rejected collaboration run
- review event emission
- task summary and artifact persistence

### CLI coverage

- `planner review-demo --json` success
- `planner review-demo --json` rejection/non-zero exit
- exact JSON contract assertions

## Risks and mitigations

### Risk: Taking on a full revision loop too early

**Mitigation**: limit this milestone to a review gate only; rejection stops the flow and records structured feedback, but does not yet create revision tasks.

### Risk: Hard-coding collaboration behavior into the runtime

**Mitigation**: add a small structured result contract instead of embedding review-specific parsing rules deep into scheduler code.

### Risk: Persona handling grows too quickly

**Mitigation**: only introduce builder and reviewer execution differences in deterministic demo flows for this milestone.

### Risk: Event schema sprawl

**Mitigation**: add only the minimum `review.*` events needed for request, feedback, approval, and rejection.

### Risk: Hidden coupling to one demo scenario

**Mitigation**: keep the scenario built-in, but define the review/result contract generically enough that future review-gated tasks can reuse it.

## Implementation-ready acceptance criteria

- A builder-reviewer collaboration scenario exists in the planner slice.
- The review input path reuses `dependency_handoffs` only, with one frozen upstream subject handoff.
- Reviewer output is machine-readable and drives runtime behavior.
- The runtime emits `review.requested`, `review.feedback`, `review.approved`, and `review.rejected` events as appropriate.
- Reviewer rejection records `review-slice` as completed, blocks downstream finalization tasks, and returns an overall structured error result.
- A nested CLI demo command exposes the collaboration slice end to end.
- Deterministic tests cover both approval and rejection paths.
- The implementation does not yet require dynamic replanning, long-lived agents, or a full revision cycle.

## Review questions before implementation

- Is a review gate without revision the right-sized next slice?
- Should the collaboration demo stay under `teamautobot planner ...`, or should it move to a separate top-level namespace later?
- Is reviewer rejection ending the run acceptable for this milestone, with revision deferred?
- Are the proposed `review.*` events the right minimal event set?

## Owner approval checklist

- [ ] The next slice should focus on builder-reviewer collaboration through a review gate.
- [ ] The milestone should stay smaller than a full revise/re-review loop.
- [ ] The review input path should reuse `dependency_handoffs` only, with a single upstream subject handoff.
- [ ] Reviewer rejection should record `review-slice` as completed, block downstream work, and surface overall CLI `status=error`.
- [ ] The structured review result and `review.*` event contracts above are the right minimum interfaces for this slice.
- [ ] Builder and reviewer are the only personas that need distinct runtime behavior in this slice.
- [ ] The collaboration demo should remain deterministic and CLI-verifiable.
- [ ] Review outcome should be machine-readable and should gate downstream execution.
- [ ] Dynamic replanning and broader agent messaging remain out of scope for this milestone.
