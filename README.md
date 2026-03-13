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
uv run python src/app.py                     # defaults to status; also accepts CLI subcommands
uv run python -m teamautobot.cli status --json
uv run python -m teamautobot.cli demo --json # writes a per-run artifact + events under .teambot/demo-runs/
uv run python -m teamautobot.cli azure-openai status --json
uv run python -m teamautobot.cli azure-openai complete --input "Say hello" --model gpt-4.1-nano --json
uv sync --group dev                              # install dev tools
uv run ruff check . && uv run ruff format .     # lint + format
```

Azure OpenAI uses the v1 Responses API via the standard `openai.OpenAI` client. Configure:

- `AZURE_OPENAI_ENDPOINT` as your resource endpoint (the CLI normalizes `/openai/v1/` automatically)
- `AZURE_OPENAI_MODEL_DEPLOYMENT`
- `AZURE_OPENAI_AUTH_MODE` as `auto`, `api_key`, or `rbac`
- `AZURE_OPENAI_API_KEY` when using API-key auth

In `auto` mode, TeamAutobot prefers API-key auth when a key is present and otherwise falls back to Microsoft Entra ID / RBAC via `DefaultAzureCredential`.

Use `azure-openai status` to verify configuration locally without making a live API call.

See [`AGENTS.md`](AGENTS.md) for architecture details, repo layout, coding conventions, and the `.agent/` workflow directory.
