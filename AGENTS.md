# AGENTS.md

## Purpose of this file

`AGENTS.md` is the high-signal repo map for humans and AI agents working in TeamAutobot.

- Keep durable rules, project identity, and navigation here.
- Keep detailed design, ADRs, plans, and workflow specifics in versioned docs under `docs/` and `.agent/`.
- If guidance starts getting long, procedural, or time-sensitive, move it to a source-of-truth document and leave a pointer here.

## Project identity

**TeamAutobot** is the repository/project and the product/system being built here. It is intended as an evolution of [TeamBot](https://github.com/glav/teamautobot) in intent, even if the implementation becomes a complete rewrite. TeamAutobot is being designed around goal-driven multi-agent collaboration with stateful agents, a typed event bus, dynamic task graphs, and hierarchical context management.

`docs/teamautobot-design.md` is the authoritative design specification and should be consulted before making architectural decisions.

Naming matters:

- Use **TeamAutobot** as the repository/project name.
- Use **TeamAutobot** as the product/system name.
- Use **TeamBot v2** only as informal shorthand for the intended evolution of TeamBot, not as the formal product name.
- Do **not** use the phrase **TeamAutobot v2**.

## Read these first

| Path | Why it matters |
|------|----------------|
| `README.md` | Quick orientation for the repository |
| `docs/teamautobot-design.md` | Authoritative v2 design and open decisions |
| `docs/decision-records/` | Accepted/proposed architectural decisions |
| `docs/plans/` | Source-controlled implementation and research plans |
| `docs/sdd-objective-template.md` | Objective format used to define work |
| `.agent/commands/sdd/README.md` | Overview of the SDD workflow |
| `.agent/standards/decision-record-standards.md` | ADR authoring rules |
| `.agent/standards/task-planning-template.md` | Planning structure and expectations |

## Operating principles

1. **Autonomy over control** — agents decide _how_; the orchestrator defines _what_ and constraints.
2. **Collaboration over handoffs** — agents communicate through shared state and events, not brittle file handoffs.
3. **Adaptation over rigidity** — plans should be able to re-shape when execution reveals new information.
4. **Tools over text** — agents should use real tools, files, tests, and terminals rather than simulated reasoning alone.
5. **Memory over repetition** — preserve useful context in repo artifacts and structured summaries instead of repeatedly re-explaining it.
6. **Observability over opacity** — actions, events, decisions, and artifacts should be traceable.
7. **Sustainable design over short-term convenience** — favor single responsibility, pragmatic SOLID boundaries, composition over inheritance, and stable interfaces.
8. **Harnessability over hidden interaction** — anything that can be done interactively should also be invocable via CLI or batch with output that is easy to verify in automation.
9. **Repository knowledge over chat memory** — repo-local, versioned artifacts are the system of record.

## Architecture snapshot

```text
OBJECTIVE INPUT
    ↓
GOAL PLANNER
    ↓
EVENT BUS
    ↓
PM / BA / Builder ×N / Reviewer / Writer
    ↓
SHARED WORKSPACE (repo + artifacts + context store)
```

Key points:

- The Goal Planner decomposes objectives into a task graph, assigns work, and can re-plan after milestones.
- Agents are persona templates, not fixed slots. Builders can fan out to `N` concurrent agents when the task graph allows it.
- The Event Bus carries typed events such as `task.*`, `agent.*`, `review.*`, `artifact.*`, and `system.*`.
- The Context Store should prefer summaries by default, with deeper artifacts and retrieval available on demand.
- TeamAutobot owns its runtime boundaries. Supporting libraries are allowed, but they should not own task scheduling, agent lifecycle, event semantics, or the memory/session model.

For full detail and current open decisions, see `docs/teamautobot-design.md` and the ADRs under `docs/decision-records/`.

## Repo map

### Current important files

- `src/app.py` — current placeholder entrypoint
- `src/load_env.py` — `.env` discovery and `python-dotenv` loading
- `pyproject.toml` / `uv.lock` — Python project metadata and dependency lockfile
- `teambot.json` / `stages.yaml` — TeamBot v1 configuration artifacts being superseded
- `.teambot/` — TeamBot v1 working directory

### Planned v2 package shape

All new v2 code should live under `src/teamautobot/`.

```text
src/teamautobot/
├── cli.py
├── planner/
├── agents/
├── events/
├── context/
└── llm/
```

## Engineering guardrails

- Target Python 3.12+.
- Use `asyncio` for concurrent agent execution and eventing.
- Use type hints throughout.
- Prefer dataclasses or Pydantic models for structured state, events, and task graph objects.
- Prefer composition over inheritance.
- Keep planner, runtime, transport, provider, and persistence concerns decoupled behind stable interfaces.
- Validate data at boundaries instead of building on guessed shapes.
- Favor boring, legible patterns when they improve maintainability and agent reasoning.
- New features should be designed so they can be exercised and verified through CLI/scriptable paths, not only interactive flows.

## Working in this repo

### Setup and local run

```bash
uv sync
cp .env-sample .env
uv run python src/app.py
```

As the v2 package takes shape, prefer:

```bash
uv run python -m teamautobot.cli
```

### Quality checks

Tests live in `tests/` and use `pytest`, `pytest-cov`, and `pytest-mock`.

```bash
uv run pytest
uv sync --group dev
uv run ruff check .
uv run ruff format .
```

For clean changes before commit:

```bash
uv run ruff format .
uv run ruff check . --fix
uv run ruff format --check .
```

No build/deploy pipeline is defined yet.

## AI-assisted workflow map

- `.agent/commands/` contains prompt files invoked as slash commands.
- `.agent/commands/sdd/README.md` documents the 9-step Spec-Driven Development workflow.
- `.agent/instructions/` contains contextual implementation guidance.
- `.agent/standards/` contains templates and standards that generated docs should follow.

Helpful devcontainer tools:

```bash
copilot
teambot init
teambot run objectives/my-feature.md
```

Use `docs/sdd-objective-template.md` when authoring new objective files.

## Documentation and ADR rules

- Store ADRs under `docs/decision-records/`.
- Store repository-tracked plans under `docs/plans/`.
- Do not create or use a top-level `decision-records/` directory.
- Use dated kebab-case ADR filenames, for example `docs/decision-records/2026-03-12-custom-agent-runtime.md`.
- New or revised ADRs should default to `Proposed`.
- Only move an ADR to `Accepted` after explicit approval from the repository owner/user.
- Do not keep repo-facing plans only in session artifacts or agent memory; mirror them into `docs/` for review and source control.
- Keep this file focused; move detailed process and evolving guidance into versioned repo docs.

## Security and troubleshooting

- Never commit `.env` or real API keys.
- Treat values in `.env` as secrets.
- Prefer devcontainer or CI secret storage for production-like runs.
- If `.env` is not loading, verify you are running from the repo root and that `.env` exists.
- If imports fail, run from the repo root or use `python -m teamautobot.<module>`.
