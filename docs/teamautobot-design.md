# TeamBot v2 — Redesign Specification

**Status**: DRAFT — Awaiting technology deep dives
**Author**: PM Agent
**Created**: 2026-03-12

---

## 1. Executive Summary

TeamBot v1 achieves its stated goal — orchestrating multiple AI agents to develop software — but does so via a **linear prompt pipeline** that limits agent autonomy, prevents real collaboration, and cannot adapt to unexpected findings. The agents are stateless LLM calls, not autonomous participants.

TeamBot v2 redesigns the system around **goal-driven agent collaboration** where agents are stateful, tool-wielding participants that communicate, negotiate, and adapt — while the orchestrator sets objectives and constraints rather than micromanaging execution.

### What Changes

| Aspect | v1 (Current) | v2 (Proposed) |
|--------|--------------|---------------|
| Orchestration | Linear 11-stage pipeline | Goal-driven planner with dynamic task decomposition |
| Agents | Stateless one-shot LLM calls | Stateful processes with tools, memory, and communication |
| Communication | None (file handoffs via orchestrator) | Event-driven message bus with structured protocols |
| Workflow | Rigid state machine | Emergent from agent interactions, bounded by constraints |
| Context | Full artifact dumping (truncation on overflow) | Hierarchical summarization + semantic retrieval |
| Autonomy | Zero (orchestrator decides everything) | High (agents select tasks, request help, negotiate) |

### What We Keep

- **Persona specialization** — Different roles with distinct capabilities
- **Review loop pattern** — Work → Review → Revise (with more flexibility)
- **Resumability** — Pick up where you left off after interruption
- **Artifact-based outputs** — Tangible deliverables at each milestone
- **Git checkpoints** — Commit after meaningful progress for rollback
- **Objective-driven** — Everything starts from a clear objective file

---

## 2. Design Principles

These principles guide every architectural decision in v2:

1. **Autonomy over control** — Agents decide _how_ to achieve goals. The orchestrator defines _what_ and _constraints_, not step-by-step instructions.

2. **Collaboration over handoffs** — Agents communicate directly, ask questions, negotiate disagreements, and coordinate work — not just pass files through a central hub.

3. **Adaptation over rigidity** — The system re-plans when reality diverges from the plan. Failed tests inform next steps. Discovered complexity triggers scope adjustments.

4. **Tools over text** — Agents interact with the real environment (files, terminal, tests, linters) rather than producing text and hoping the orchestrator acts on it.

5. **Memory over repetition** — Agents retain relevant context across interactions. Smart summarization replaces context dumping.

6. **Observability over opacity** — Every agent action, decision, and communication is traceable. You can understand _why_ the system did what it did.

7. **Minimal viable framework** — Build only what's needed. Avoid heavy frameworks that impose their own opinions. Prefer composable primitives.

---

## 3. Proposed Architecture

### 3.1 High-Level Overview

```
┌─────────────────────────────────────────────────────┐
│                   OBJECTIVE INPUT                    │
│          (markdown file with frontmatter)            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│                  GOAL PLANNER                        │
│  Decomposes objective → task graph                   │
│  Re-plans after each milestone                       │
│  Manages dependencies and priorities                 │
└──────────────────────┬──────────────────────────────┘
                       │ task assignments
                       ▼
┌─────────────────────────────────────────────────────┐
│                  EVENT BUS                           │
│  Structured messages between all components          │
│  Event types: task.*, agent.*, review.*, system.*    │
│  Persistent log for replay and debugging             │
└───┬─────────┬─────────┬─────────┬──────────────┬───┘
    │         │         │         │              │
    ▼         ▼         ▼         ▼              ▼
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐   ┌──────────┐
│  PM   │ │  BA   │ │Builder│ │Builder│   │ Reviewer  │
│ Agent │ │ Agent │ │   1   │ │   2   │   │  Agent   │
├───────┤ ├───────┤ ├───────┤ ├───────┤   ├──────────┤
│Memory │ │Memory │ │Memory │ │Memory │   │Memory    │
│Tools  │ │Tools  │ │Tools  │ │Tools  │   │Tools     │
│Persona│ │Persona│ │Persona│ │Persona│   │Persona   │
└───────┘ └───────┘ └───────┘ └───────┘   └──────────┘
    │         │         │         │              │
    └─────────┴─────────┴─────────┴──────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│                SHARED WORKSPACE                      │
│  Git repo │ Artifact store │ Context store           │
└─────────────────────────────────────────────────────┘
```

### 3.2 Core Components

#### 3.2.1 Goal Planner (replaces Orchestrator + WorkflowStateMachine)

The Goal Planner replaces the rigid 11-stage pipeline with dynamic task decomposition.

**Responsibilities**:
- Parse objective file into a structured goal
- Decompose goal into a **task graph** (DAG, not linear list)
- Assign tasks to agents based on persona capabilities
- **Re-plan** after each task completion based on actual outcomes
- Detect blockers and reassign work
- Determine when the objective is complete (acceptance criteria met)

**Key Behaviors**:
- **Initial plan**: Creates first-pass task graph from objective
- **Adaptive re-planning**: After each task completes, evaluates:
  - Did the outcome match expectations?
  - Are new tasks needed based on discoveries?
  - Should existing tasks be modified or cancelled?
  - Can more tasks now run in parallel?
- **Constraint enforcement**: Ensures agents stay within scope, budget, and quality bounds
- **Completion detection**: Checks acceptance criteria from objective, not stage count

**Task Graph Example**:
```
objective: "Add user authentication"
├── define-requirements (BA)
│   └── depends: objective
├── research-auth-patterns (Builder-1)
│   └── depends: define-requirements
├── create-impl-plan (PM)
│   └── depends: research-auth-patterns
├── implement-auth-module (Builder-1)    ─┐
│   └── depends: create-impl-plan         │ parallel
├── implement-auth-tests (Builder-2)     ─┘
│   └── depends: create-impl-plan
├── review-implementation (Reviewer)
│   └── depends: implement-auth-module, implement-auth-tests
├── address-review-feedback (Builder-1)       ← created dynamically
│   └── depends: review-implementation        ← only if review has feedback
├── acceptance-validation (Builder-1)
│   └── depends: review-implementation [approved]
└── final-review (PM + Reviewer)
    └── depends: acceptance-validation [passed]
```

**What It Does NOT Do**:
- Does not execute tasks (agents do that)
- Does not dictate _how_ agents perform tasks
- Does not manage LLM calls directly

#### 3.2.2 Agent Model (replaces AgentRunner + stateless LLM calls)

Each agent is a **stateful, tool-wielding process** with a persistent identity.

**Agent Anatomy**:
```
┌─────────────────────────────┐
│          AGENT              │
├─────────────────────────────┤
│ Persona    │ Role, capabilities, constraints     │
│ Memory     │ Working memory (current task state)  │
│            │ Long-term memory (session history)    │
│ Tools      │ Role-appropriate tool access          │
│ Inbox      │ Event subscriptions                   │
│ Outbox     │ Event emissions                       │
│ LLM        │ Model + system prompt                 │
└─────────────────────────────┘
```

**Agent Lifecycle**:
1. **Spawn**: Created by Goal Planner when needed (not all at once)
2. **Idle**: Waiting for task assignment or relevant event
3. **Working**: Executing a task using tools and LLM reasoning
4. **Communicating**: Asking questions, providing feedback, negotiating
5. **Complete**: Task finished, results published, returns to idle
6. **Shutdown**: No more tasks, agent terminated

**Agent Tool Access by Persona**:

| Persona | Tools |
|---------|-------|
| PM | Task graph read/write, progress queries, agent messaging |
| BA | Codebase search, file reading, requirement templates, agent messaging |
| Builder | File read/write, terminal execution, test runner, linter, debugger, git operations, agent messaging |
| Reviewer | File reading, diff viewer, static analysis runner, test runner, coverage checker, agent messaging |
| Writer | File read/write, doc generation, link checking, agent messaging |

**Agent Memory Model**:
- **Working memory**: Current task, recent actions, pending questions (cleared per task)
- **Session memory**: Summarized history of all tasks completed this run (persists across tasks)
- **Retrieval**: Agent can query context store for specific information from previous tasks/artifacts

#### 3.2.3 Event Bus (replaces unused MessageRouter)

All communication flows through a persistent, typed event bus.

**Event Categories**:

| Category | Events | Purpose |
|----------|--------|---------|
| `task.*` | `task.assigned`, `task.started`, `task.completed`, `task.failed`, `task.blocked` | Task lifecycle |
| `agent.*` | `agent.question`, `agent.answer`, `agent.status`, `agent.handoff` | Agent communication |
| `review.*` | `review.requested`, `review.feedback`, `review.approved`, `review.rejected` | Review workflow |
| `artifact.*` | `artifact.created`, `artifact.updated`, `artifact.validated` | Artifact lifecycle |
| `system.*` | `system.replan`, `system.checkpoint`, `system.error`, `system.complete` | System events |

**Event Structure**:
```
{
  "id": "uuid",
  "type": "review.feedback",
  "source": "reviewer",
  "target": "builder-1",        // null for broadcasts
  "timestamp": "ISO-8601",
  "correlation_id": "task-uuid", // links related events
  "payload": { ... }            // type-specific data
}
```

**Key Properties**:
- **Persistent**: All events logged to disk for replay and debugging
- **Ordered**: Within a correlation chain, events are strictly ordered
- **Filterable**: Agents subscribe to event types relevant to their role
- **Replay-safe**: System can resume from any event in the log

#### 3.2.4 Context Management (replaces full-artifact dumping)

**Three-Tier Context System**:

| Tier | What | When Used | Storage |
|------|------|-----------|---------|
| **Summary** | 2-3 sentence digest of each artifact/task | Default context for all agents | In-memory + disk |
| **Artifact** | Full output of each completed task | On-demand when agent needs detail | Disk (markdown files) |
| **Semantic** | Indexed chunks for targeted retrieval | When agent queries specific information | Context store |

**Context Flow**:
1. Agent completes task → produces artifact (full output)
2. System generates summary of artifact (LLM-generated digest)
3. Summary added to session context (all agents can see)
4. Artifact stored in artifact store (available on request)
5. Artifact indexed in context store (queryable by content)

**Agent Context Loading**:
- Agent receives: persona prompt + task description + session summaries
- Agent can request: full artifacts, semantic search results, file contents
- **No more context explosion**: Summaries keep base context small; agents pull details as needed

#### 3.2.5 Workflow Model (replaces rigid state machine)

v2 has **no predefined workflow stages**. Instead, workflow emerges from:

1. **Goal Planner** decomposes objective into task graph
2. **Agents** execute tasks and emit events
3. **Goal Planner** re-evaluates and extends task graph
4. **Completion** when acceptance criteria from objective are met

**Guardrails** (to prevent unbounded execution):
- **Max iterations**: Configurable limit on total task count
- **Max duration**: Wall-clock timeout for entire objective
- **Review gates**: Certain task types (implementation, documentation) always require review
- **Acceptance criteria**: Objective defines measurable completion conditions
- **Human escalation**: If agents are stuck (N consecutive failures), pause and notify

**Common Workflow Patterns** (emerge naturally, not enforced):

```
Simple feature:
  define → plan → implement → review → test → done

Complex feature:
  define → research → plan → [implement-A, implement-B] → review →
  address-feedback → re-review → test → fix-failures → re-test → done

Bug fix:
  reproduce → diagnose → fix → test → review → done

Documentation:
  analyze-code → draft-docs → review → revise → done
```

---

## 4. Technology Decisions

> ⚠️ **The following sections require deep-dive evaluation before committing.**
> Each decision is presented with options, trade-offs, and open questions.

### 4.1 Agent Framework

**Status**: 🟡 PROPOSED — Build custom runtime from composable primitives

**Current proposal**: TeamAutobot should implement its core agent runtime in-repo. Lightweight libraries may be used for spikes or narrow supporting concerns, but not as the owning runtime or orchestration layer.

#### Option A: Build Custom (Leading Direction)

Build a minimal agent runtime from composable primitives.

**Components to build**:
- Agent loop (receive task → reason → act → emit result)
- Tool registry (register/invoke tools per persona)
- Memory manager (working + session memory)
- Event bus adapter (publish/subscribe)

**Pros**:
- Full control over agent behavior and lifecycle
- No framework lock-in or imposed opinions
- Can optimize for TeamBot's specific needs
- Simpler debugging (no framework abstractions to trace through)
- Aligns with Principle 7 (minimal viable framework)

**Cons**:
- More upfront development effort
- Must build tool-calling, retry logic, error handling from scratch
- No community ecosystem of pre-built integrations

**Why this is the leading direction**:
- Best fit for TeamAutobot's need for dynamic task graphs, explicit agent lifecycles, and dynamic agent fan-out
- Keeps event semantics, replayability, and observability first-class and repo-owned
- Avoids coupling the system's core behavior to another framework's abstractions
- Still allows narrow helper dependencies without handing over orchestration control

#### Option B: Use an External Agent Library or Framework

Use a library or framework that provides useful runtime capabilities without forcing TeamAutobot into the wrong orchestration model.

**Candidates to evaluate**:
- **Pydantic AI** — Type-safe agent framework, lightweight, good tool calling
- **Mirascope** — Minimal LLM toolkit with structured outputs
- **Instructor** — Structured output extraction (not a full agent framework)
- **AutoGen** — Event-driven multi-agent framework with team abstractions; important prior art and still relevant for comparison
- **Microsoft Agent Framework** — Full agent/workflow runtime with sessions, middleware, events, and graph orchestration
- **Marvin** — Lightweight AI functions and tools
- **smolagents (HuggingFace)** — Minimal agent framework, tool-use focused

**Pros**:
- Faster development (tool calling, retries, structured output handled)
- Community maintenance of LLM provider integrations
- Type safety and validation built in

**Cons**:
- Another dependency to manage and keep updated
- May impose subtle constraints on agent design
- Framework bugs become your bugs
- Still unlikely to remove the need for custom orchestration, eventing, and lifecycle control
- Some candidates, especially AutoGen and Microsoft Agent Framework, bring larger runtime models that may shape the system more than intended

#### Option C: ~~Heavy Frameworks (LangGraph, CrewAI)~~

**Ruled out** per stakeholder direction. These impose too much opinion on workflow structure and agent interaction patterns, conflicting with our goal of emergent behavior.

**Position on external libraries/frameworks**:
- **PydanticAI** remains the strongest comparison point because of structured outputs, validation, and observability
- **smolagents** and **Mirascope** are better viewed as prototype aids than as the foundation for the runtime
- **AutoGen** should be considered explicitly because of its event-driven runtime and historical influence, but it is likely a secondary comparison behind Microsoft Agent Framework because Microsoft positions Agent Framework as its forward path
- **Microsoft Agent Framework** is a serious framework candidate and should be treated separately from thin helper libraries because it includes workflows, state/session handling, middleware, events, and checkpointing
- **Marvin** and similar frameworks remain too opinionated for the architecture we want

**Follow-up Questions**:
- [ ] What is the minimum viable custom agent loop for Phase 1?
- [ ] What abstractions must stay internal so D2 (LLM interface) can evolve independently?
- [ ] What retry/error model belongs in the runtime versus the LLM client layer?
- [ ] What observability and replay hooks must be present from day one?

---

### 4.2 LLM Interface

**Status**: 🔴 OPEN — Requires deep dive

**Decision**: How do agents call LLMs? Continue with Copilot SDK or go direct?

#### Option A: Continue with GitHub Copilot SDK

**Current approach**: `github-copilot-sdk==0.1.32`

**Pros**:
- Already integrated and working
- Handles authentication via GitHub
- Access to multiple model providers through single API

**Cons**:
- Pinned to specific version (0.1.32) — SDK maturity unclear
- Adds abstraction layer between agents and LLMs
- May limit tool-calling capabilities vs. direct API
- Dependency on GitHub infrastructure

#### Option B: Direct LLM Provider APIs

Use provider SDKs directly (Anthropic, OpenAI, etc.)

**Pros**:
- Full access to latest features (tool calling, structured output, streaming)
- No intermediary SDK version constraints
- Better error messages and debugging
- Provider-specific optimizations

**Cons**:
- Must manage multiple provider integrations
- Authentication per provider
- More configuration complexity

#### Option C: LLM Gateway / Abstraction

Use a thin abstraction (e.g., LiteLLM, custom interface) over multiple providers.

**Pros**:
- Single interface, multiple backends
- Easy model switching
- Can add local models later

**Cons**:
- Another dependency
- Abstraction may lag behind provider features

**Open Questions**:
- [ ] Does the Copilot SDK support tool calling / function calling well enough for v2?
- [ ] What's the Copilot SDK roadmap? Is it actively maintained?
- [ ] Do we need streaming responses for agent interaction?
- [ ] What's our model strategy? Single provider or multi-provider?

---

### 4.3 Event Bus / Message Transport

**Status**: 🔴 OPEN — Requires deep dive

**Decision**: How do agents communicate? What transports the events?

#### Option A: In-Process Event System (Start Here)

Python async event bus using `asyncio.Queue` or a simple pub/sub.

**Pros**:
- Zero external dependencies
- Simple to implement and debug
- Sufficient for single-machine execution
- Easy to add persistence (append events to JSONL file)

**Cons**:
- Single process only (no distributed agents)
- Must handle backpressure manually

#### Option B: File-Based Event Log

Events appended to a JSONL file. Agents poll or use file watchers.

**Pros**:
- Dead simple persistence
- Easy to inspect and debug
- Works across processes

**Cons**:
- Polling latency or file watcher complexity
- No built-in ordering guarantees across writers

#### Option C: External Message Broker (Redis Streams, NATS, etc.)

**Pros**:
- Battle-tested pub/sub semantics
- Built-in persistence and replay
- Scales to distributed agents

**Cons**:
- External dependency (must run a server)
- Operational overhead
- Overkill for single-machine use case

**Recommendation**: Start with Option A (in-process), persist to JSONL for replay. Design the event interface so transport can be swapped later.

**Open Questions**:
- [ ] Do we need distributed agent execution? Or is single-machine sufficient?
- [ ] What's the expected event volume? (Likely low — dozens per objective, not thousands)
- [ ] Do we need real-time event streaming to a UI?

---

### 4.4 Context Store

**Status**: 🔴 OPEN — Requires deep dive

**Decision**: How do agents retrieve relevant context from previous work?

#### Option A: Structured File Store + LLM Summarization

- Artifacts stored as markdown files (like v1)
- Summaries generated by LLM after each task
- Agents receive summaries by default, request full artifacts on demand

**Pros**:
- Simple, no new infrastructure
- Human-readable on disk
- Summaries keep context small

**Cons**:
- No semantic search (can't find "the part about rate limiting")
- Summary quality depends on LLM

#### Option B: File Store + Embedding-Based Retrieval

- Same file store as Option A
- Additionally index artifact chunks into a vector store
- Agents can query: "What did the spec say about error handling?"

**Candidates**: ChromaDB (embedded), SQLite + FTS5, LanceDB

**Pros**:
- Semantic search for targeted context
- Agents get exactly the information they need
- Scales better for large objectives

**Cons**:
- Additional dependency (vector DB or embedding model)
- Index maintenance overhead
- Embedding quality affects retrieval quality

#### Option C: Hybrid (Recommended Direction)

- Summaries for default context (cheap, fast)
- Full artifacts on disk (always available)
- SQLite FTS5 for keyword search (no external dependency)
- Optional vector search for large objectives (future enhancement)

**Open Questions**:
- [ ] How large are typical objectives? How many artifacts per run?
- [ ] Is keyword search (FTS5) sufficient, or do we need semantic search?
- [ ] What's the cost of generating summaries after each task?
- [ ] Should context store persist across runs (learning from past objectives)?

---

### 4.5 CLI & User Interface

**Status**: 🟡 PARTIALLY DECIDED

**Decision**: Keep CLI-first approach. Enhance observability.

**Keep from v1**:
- `teambot init` / `teambot run` / `teambot status` command structure
- Objective file input format (markdown with frontmatter)
- Rich console output

**Add in v2**:
- **Live dashboard**: Real-time view of agent activity, task graph, events
- **Event log viewer**: Inspect the event bus history
- **Intervention mode**: Human can pause, redirect, or override agents
- **Replay mode**: Re-run from any point in the event log

---

## 5. Retained From v1

These v1 concepts carry forward into v2:

| Concept | v1 Implementation | v2 Evolution |
|---------|-------------------|--------------|
| Personas | 6 static templates | 6 personas with dynamic capabilities and tools |
| Objective files | Markdown + YAML frontmatter | Same format, enhanced frontmatter schema |
| Review loops | Fixed 4-iteration limit | Dynamic iteration until approval or escalation |
| Git checkpoints | Commit after each stage | Commit after each meaningful milestone |
| Resumability | JSON state file | Event log replay (richer, more granular) |
| Artifact outputs | Markdown files in `.teambot/` | Same location, with added summaries |
| CLI interface | init/run/status | Same commands, enhanced with dashboard and replay |
| Acceptance tests | pytest-based validation | Same approach, with smarter retry logic |

---

## 6. What We Remove From v1

| Component | Why |
|-----------|-----|
| `window_manager.py` | Dead code. Agents are not terminal processes. |
| `messaging/router.py` | Dead code. Replaced by Event Bus. |
| `messaging/protocol.py` | Dead code. Replaced by new event schema. |
| `agent_runner.py` (legacy) | Replaced by new Agent Model. |
| `orchestrator.py` (legacy) | Replaced by Goal Planner. |
| `workflow/state_machine.py` | Replaced by task graph + event log. |
| Rigid 11-stage pipeline | Replaced by emergent workflow from goal decomposition. |
| Full-context dumping | Replaced by hierarchical summarization. |

---

## 7. Migration Strategy

### Phase 1: Foundation
- Build core agent runtime (agent loop, tool registry, memory)
- Build event bus (in-process with JSONL persistence)
- Build context manager (summaries + artifact store)
- Port persona definitions to new agent model
- **Milestone**: Single agent can receive a task, use tools, and produce an artifact

### Phase 2: Multi-Agent Collaboration
- Build Goal Planner (objective → task graph)
- Implement agent-to-agent communication via event bus
- Build review workflow (request → feedback → revision cycle)
- **Milestone**: Two agents (builder + reviewer) can collaborate on a task

### Phase 3: Full Team
- Enable all 6 personas with appropriate tools
- Implement dynamic re-planning
- Build acceptance test integration
- Add git checkpoint management
- **Milestone**: Full team can complete a simple objective autonomously

### Phase 4: Polish & Observability
- Live dashboard for agent activity
- Event log viewer and replay
- Intervention mode (human override)
- Performance optimization (parallel agent execution)
- **Milestone**: Production-ready for real objectives

---

## 8. Open Decision Log

Decisions that require deep-dive evaluation before Phase 1 can begin:

| ID | Decision | Options | Status | Notes |
|----|----------|---------|--------|-------|
| D1 | Agent framework | Custom build vs. lightweight library | 🟡 PROPOSED | Current leading direction is a custom runtime; await explicit approval after ADR revisions |
| D2 | LLM interface | Copilot SDK vs. direct API vs. gateway | 🔴 OPEN | Depends on tool-calling requirements |
| D3 | Event transport | In-process vs. file-based vs. broker | 🟡 LEANING | In-process + JSONL likely sufficient |
| D4 | Context retrieval | Summaries only vs. FTS5 vs. vector | 🟡 LEANING | Hybrid (summaries + FTS5) likely sufficient |
| D5 | Agent persistence | Long-lived processes vs. spawn-per-task | 🔴 OPEN | Affects memory model and resource usage |
| D6 | Python version | 3.11+ (current) vs. 3.12+ | 🟢 LOW RISK | 3.12+ for better asyncio and typing |
| D7 | Testing strategy | How to test multi-agent interactions | 🔴 OPEN | Need deterministic replay for CI |
| D8 | Objective format | Keep v1 format vs. enhance | 🟡 LEANING | Keep format, extend frontmatter schema |

---

## 9. Success Criteria

v2 is successful when:

1. **Autonomy**: Agents complete a medium-complexity objective with zero human intervention
2. **Adaptation**: System recovers from a failed test by diagnosing, fixing, and re-testing without manual intervention
3. **Collaboration**: Agents communicate to resolve ambiguity (builder asks BA a clarifying question, gets answer, proceeds)
4. **Observability**: A human can review the event log and understand every decision the system made
5. **Resumability**: System can resume from any point after interruption
6. **Quality**: Output quality meets or exceeds v1 for equivalent objectives
7. **Flexibility**: New persona or workflow pattern can be added without modifying core framework

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Goal Planner** | Component that decomposes objectives into task graphs and re-plans adaptively |
| **Task Graph** | DAG of tasks with dependencies, assigned to agents |
| **Event Bus** | Communication backbone; all agent and system events flow through it |
| **Agent** | Stateful process with persona, tools, memory, and LLM access |
| **Persona** | Role definition (PM, BA, Builder, Reviewer, Writer) with capabilities and constraints |
| **Artifact** | Tangible output of a completed task (spec, plan, code, review) |
| **Summary** | LLM-generated digest of an artifact for compact context |
| **Context Store** | Indexed repository of artifacts and summaries for agent retrieval |
| **Working Memory** | Per-task agent state (cleared between tasks) |
| **Session Memory** | Per-run agent state (summarized history of completed tasks) |
| **Guardrail** | Constraint that prevents unbounded execution (max iterations, timeout, etc.) |
