# TeamAutobot

The repository for **TeamAutobot**, an AI agent orchestration system intended as an evolution of [TeamBot](https://github.com/glav/teamautobot), even if the implementation becomes a complete rewrite.

**TeamBot v1** used a linear 11-stage pipeline with stateless LLM calls. **TeamAutobot** replaces that with goal-driven collaboration: stateful agents, a dynamic task graph, an event bus for inter-agent communication, and hierarchical context management.

See [`docs/teamautobot-design.md`](docs/teamautobot-design.md) for the full design specification.

## Key concepts

- **Goal Planner** decomposes objectives into a task graph (DAG), assigns work to agents, and re-plans adaptively
- **Agent Pool** spawns stateful agents on demand — personas are templates, not fixed slots (e.g. N builders can fan out for parallel work)
- **Event Bus** provides typed, persistent messaging between all agents and system components
- **Context Store** uses three-tier retrieval (summaries → full artifacts → semantic search) instead of context dumping

## Setup

Requires [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync
cp .env-sample .env  # fill in values
```

## Development

```bash
uv run python src/app.py          # current placeholder entrypoint
uv sync --group dev               # install dev tools
uv run ruff check . && uv run ruff format .  # lint + format
```

See [`AGENTS.md`](AGENTS.md) for architecture details, repo layout, coding conventions, and the `.agent/` workflow directory.
