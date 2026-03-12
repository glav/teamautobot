# AGENTS.md

## Project overview

**TeamAutobot** is the repository/project for **TeamBot v2**, the next iteration of [TeamBot](https://github.com/glav/teamautobot) — a system that orchestrates multiple AI agents to collaboratively develop software. Where TeamBot v1 uses a linear 11-stage prompt pipeline with stateless LLM calls, TeamBot v2 is built around **goal-driven agent collaboration** with stateful agents, an event bus, dynamic task graphs, and hierarchical context management.

**Design reference**: `docs/teamautobot-design.md` is the authoritative design specification. Always consult it before making architectural decisions.

### Key design principles

1. **Autonomy over control** — Agents decide _how_; the orchestrator defines _what_ and _constraints_
2. **Collaboration over handoffs** — Agents communicate directly via an event bus, not file handoffs
3. **Adaptation over rigidity** — Dynamic re-planning when reality diverges from the plan
4. **Tools over text** — Agents interact with real environments (files, terminal, tests, linters)
5. **Memory over repetition** — Hierarchical summarisation replaces full-context dumping
6. **Observability over opacity** — Every action, decision, and message is traceable
7. **Minimal viable framework** — Composable primitives, not heavy frameworks

### Architecture overview

```
OBJECTIVE INPUT (markdown + frontmatter)
        │
        ▼
   GOAL PLANNER — decomposes objective → task graph (DAG), re-plans adaptively
        │
        ▼
   EVENT BUS — structured typed events (task.*, agent.*, review.*, artifact.*, system.*)
        │
   ┌────┼────┬──────────────────────┬──────────┐
   ▼    ▼    ▼                      ▼          ▼
  PM   BA  Builder ×N (fan-out)  Reviewer   Writer
  (each: persona + memory + tools + inbox/outbox + LLM)
        │
        ▼
   SHARED WORKSPACE — git repo + artifact store + context store
```

**Core components**:

| Component | Purpose | Replaces (v1) |
|-----------|---------|---------------|
| **Goal Planner** | Decomposes objectives into task graphs (DAGs), assigns to agents, re-plans after milestones | Orchestrator + WorkflowStateMachine |
| **Agent Pool** | Dynamic pool of stateful agent instances; the Goal Planner spawns as many as the task graph demands | Fixed 6-agent roster |
| **Agent Model** | Stateful processes with persona, working/session memory, role-specific tools, event inbox/outbox | AgentRunner + stateless LLM calls |
| **Event Bus** | Persistent typed message bus for all agent and system communication | Unused MessageRouter |
| **Context Store** | Three-tier system: summaries (default), full artifacts (on-demand), semantic retrieval (FTS5) | Full-artifact context dumping |

### Dynamic agent spawning

v1 hard-coded exactly 6 agent slots (PM, BA, Builder-1, Builder-2, Reviewer, Writer). v2 removes that ceiling:

- **Personas are templates, not fixed slots.** The Goal Planner can spawn _N_ builders (or reviewers, etc.) based on the parallelism available in the task graph.
- **Fan-out on demand.** If a plan has 5 independent implementation tasks, the planner can spin up 5 builder agents to work them concurrently.
- **Fan-in after completion.** Once parallel work converges (e.g. review gate), surplus agents are released.
- **Any persona can scale.** Builders are the most obvious fan-out candidate, but the same mechanism works for reviewers (parallel review of independent modules) or writers (parallel doc generation).
- **Resource-bounded.** Configurable concurrency limits prevent runaway agent creation (max total agents, max per-persona, etc.).

### Agent personas and tool access

| Persona | Scalable | Tools |
|---------|----------|-------|
| PM | Typically 1 | Task graph read/write, progress queries, agent messaging |
| BA | As needed | Codebase search, file reading, requirement templates, agent messaging |
| Builder | Fan-out | File read/write, terminal, test runner, linter, debugger, git, agent messaging |
| Reviewer | As needed | File reading, diff viewer, static analysis, test runner, coverage, agent messaging |
| Writer | As needed | File read/write, doc generation, link checking, agent messaging |

### Migration phases

| Phase | Goal | Milestone |
|-------|------|-----------|
| **1 — Foundation** | Core agent runtime, event bus, context manager, persona definitions | Single agent can receive task, use tools, produce artifact |
| **2 — Multi-Agent** | Goal Planner, agent-to-agent communication, review workflow | Two agents (e.g. builder + reviewer) collaborate on a task |
| **3 — Full Team** | All personas with dynamic spawning, re-planning, acceptance tests, git checkpoints | Team of dynamically-scaled agents completes a simple objective autonomously |
| **4 — Polish** | Live dashboard, event log viewer, replay, intervention mode, concurrency tuning | Production-ready for real objectives |

### Open technology decisions

Consult `docs/teamautobot-design.md` §4 and §8 for full context on these:

| ID | Decision | Leaning |
|----|----------|---------|
| D1 | Agent framework | Custom build vs lightweight library (Pydantic AI, smolagents) |
| D2 | LLM interface | Copilot SDK vs direct API vs gateway (LiteLLM) |
| D3 | Event transport | In-process asyncio + JSONL persistence (likely) |
| D4 | Context retrieval | Summaries + FTS5 hybrid (likely) |
| D5 | Agent persistence | Long-lived processes vs spawn-per-task |
| D7 | Testing strategy | Deterministic replay for CI |

## Repo layout

### Current state (pre-v2 implementation)

- `docs/decision-records/`: architecture decision records (ADRs)
- `docs/teamautobot-design.md`: v2 design specification (authoritative)
- `docs/sdd-objective-template.md`: objective template for defining tasks
- `src/app.py`: placeholder entrypoint; calls `load_env()`
- `src/load_env.py`: `.env` discovery + `python-dotenv` loading
- `pyproject.toml`: Python project metadata + dependencies (managed by `uv`)
- `uv.lock`: resolved dependency lockfile (generated by `uv`)
- `.env-sample`: example environment variables (copy to `.env`)
- `teambot.json`: v1 TeamBot agent/workflow configuration (to be superseded)
- `stages.yaml`: v1 TeamBot stage definitions (to be superseded)
- `.teambot/`: v1 TeamBot working directory

### Planned v2 structure

As implementation progresses, the `src/` directory will grow to contain:

```
src/
├── teamautobot/
│   ├── __init__.py
│   ├── cli.py                 # CLI entrypoint (init/run/status)
│   ├── planner/               # Goal Planner — objective → task graph
│   │   ├── goal_planner.py
│   │   └── task_graph.py
│   ├── agents/                # Agent Model — dynamic agent pool
│   │   ├── base_agent.py      # Agent loop, lifecycle, memory
│   │   ├── pool.py            # Agent pool — spawn/release/concurrency limits
│   │   ├── personas/          # Persona templates (PM, BA, Builder, Reviewer, Writer)
│   │   ├── tools/             # Tool registry + role-specific tools
│   │   └── memory.py          # Working + session memory management
│   ├── events/                # Event Bus — typed pub/sub + persistence
│   │   ├── bus.py
│   │   ├── types.py           # Event schemas (task.*, agent.*, review.*, etc.)
│   │   └── store.py           # JSONL persistence + replay
│   ├── context/               # Context Store — summaries + artifacts + retrieval
│   │   ├── manager.py
│   │   ├── summarizer.py
│   │   └── store.py           # FTS5 / artifact indexing
│   └── llm/                   # LLM interface abstraction
│       └── client.py
├── app.py                     # Current placeholder (will be replaced by cli.py)
└── load_env.py                # Current placeholder (will be absorbed)
```

## Setup

### Install uv

This project uses `uv` for dependency management and virtualenv creation.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If `uv` is installed during devcontainer creation, you may need to restart the terminal so `uv` is on your `PATH`.

### Create a virtual environment + install dependencies

```bash
uv sync
```

### Environment variables

- Copy `.env-sample` to `.env` and fill in real values.
- `.env` is gitignored.

```bash
cp .env-sample .env
```

## Development workflow

### Run the app (current placeholder)

```bash
uv run python src/app.py
```

### Python conventions

- Target Python 3.12+ (for improved asyncio and typing support)
- Use `asyncio` for concurrent agent execution and event bus
- Use type hints throughout; prefer `typing` module for complex types
- Use dataclasses or Pydantic models for structured data (events, task graph nodes, agent state)
- Prefer composition over inheritance for agent and tool design

### Adding new modules

Place all v2 code under `src/teamautobot/`. The package should be importable:

```bash
uv run python -m teamautobot.cli
```

### Copilot / AI assisted workflow

- All Copilot and AI assisted workflows exist in the `.agent` directory
- GitHub Copilot CLI and TeamBot v1 are pre-installed in the devcontainer
- To start using Copilot CLI, type `copilot`
- To start using TeamBot v1, run `teambot init` then `teambot run`

### `.agent` directory structure

The `.agent` directory contains commands, instructions, and standards used by AI-assisted workflows.

#### Commands (`commands/`)

Prompt files invoked as slash commands (e.g. `/sdd:0-initialize`).

| Path | Description |
|------|-------------|
| `commands/azdo/azdo.generate-pr-description.prompt.md` | Generates pull request descriptions using Azure DevOps templates. |
| `commands/docs/docs.create-adr.prompt.md` | Creates architecture decision records following organisational standards. |
| `commands/project/proj.sprint-planning.prompt.md` | Builds sprint plans for software engineering teams to deliver implementation engagements. |
| `commands/setup/setup.agents-md-creation.prompt.md` | Generates or updates the `AGENTS.md` file for the repository. |

**Spec-Driven Development (SDD) workflow** (`commands/sdd/`)

A sequential workflow with quality gates for taking a feature from specification through to implementation.

| Path | Description |
|------|-------------|
| `commands/sdd/README.md` | Documents the SDD workflow overview and its 9 sequential steps. |
| `commands/sdd/sdd.0-initialize.prompt.md` | Initialises the SDD workflow by verifying prerequisites and creating tracking directories. |
| `commands/sdd/sdd.1-create-feature-spec.prompt.md` | Guides creation of feature specifications with Q&A and reference integration. |
| `commands/sdd/sdd.2-review-spec.prompt.md` | Reviews and validates specifications before the research phase. |
| `commands/sdd/sdd.3-research-feature.prompt.md` | Conducts comprehensive research and analysis for the feature. |
| `commands/sdd/sdd.4-determine-test-strategy.prompt.md` | Analyses specs and research to recommend an optimal testing strategy. |
| `commands/sdd/sdd.5-task-planner-for-feature.prompt.md` | Creates actionable implementation plans for the feature. |
| `commands/sdd/sdd.6-review-plan.prompt.md` | Reviews and validates implementation plans before execution. |
| `commands/sdd/sdd.7-task-implementer-for-feature.prompt.md` | Implements task plans with progressive tracking and change records. |
| `commands/sdd/sdd.8-post-implementation-review.prompt.md` | Performs post-implementation review and final validation. |

#### Instructions (`instructions/`)

Contextual guidelines automatically applied to AI interactions.

| Path | Description |
|------|-------------|
| `instructions/prompt.instructions.md` | Guidelines for creating high-quality prompt files for GitHub Copilot. |
| `instructions/bash/bash.instructions.md` | Instructions for bash script implementation with established conventions. |
| `instructions/bash/bash.md` | Guidelines for secure, maintainable bash scripting practices. |
| `instructions/bicep/bicep-standards.md` | Coding standards and best practices for Bicep Infrastructure as Code. |
| `instructions/bicep/bicep.instructions.md` | Instructions for Bicep infrastructure implementation. |
| `instructions/bicep/bicep.md` | Structural guidelines for Bicep development. |

#### Standards (`standards/`)

Templates and standards referenced by commands and instructions.

| Path | Description |
|------|-------------|
| `standards/decision-record-standards.md` | Standards for creating decision records capturing architectural and policy decisions. |
| `standards/decision-record-template.md` | Template for decision records with status, deciders, context, and consequences. |
| `standards/feature-spec-template.md` | Template for feature specification documents with progress tracking. |
| `standards/research-feature-template.md` | Template for task research documents with implementation analysis. |
| `standards/task-planning-template.md` | Template for task checklists with overview and implementation instructions. |

## Documentation conventions

- Use **TeamAutobot** as the repository/project name.
- Use **TeamBot v2** as the product/version name for the system being designed in this repository.
- Store all architecture decision records under `docs/decision-records/`.
- Do not create or use a top-level `decision-records/` directory.
- Use dated kebab-case filenames for ADRs, e.g. `docs/decision-records/2026-03-12-custom-agent-runtime.md`.
- New or revised ADRs should default to `Proposed`.
- Only move an ADR to `Accepted` after explicit approval from the repository owner/user.

## Testing

- Framework: `pytest` with `pytest-cov` and `pytest-mock`
- Tests located in `tests/` directory
- Run tests: `uv run pytest`
- v2 testing strategy (D7) is an open decision — deterministic event replay for CI is the goal

## Linting and formatting

Uses `ruff` as the linter/formatter.

```bash
uv sync --group dev
uv run ruff check .
uv run ruff format .
```

## Clean commits

When committing or changing code, always ensure properly linted code by running:

```bash
uv run ruff format .
uv run ruff check . --fix
uv run ruff format --check .
```

## Build and deployment

No build/deploy pipeline is defined yet.

## Security and secrets

- Never commit `.env` or real API keys.
- Treat values in `.env` as secrets.
- Prefer using the devcontainer/CI secret store for production-like runs.

## Troubleshooting

- If `.env` isn't being loaded, verify you are running from the repo root and that `.env` exists.
- If imports fail, run scripts from the repo root or use `python -m teamautobot.<module>`.

## Objective template

TeamBot/TeamAutobot uses objective files to define development tasks:

**File**: `docs/sdd-objective-template.md`

Copy this template, fill in the sections, then run with TeamBot v1:

```bash
teambot run objectives/my-feature.md
```
