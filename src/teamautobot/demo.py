from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from .agents import AgentTask, SingleTaskAgent
from .artifacts import ArtifactStore
from .events import EventBus, JsonlEventStore
from .llm import (
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    ModelSelection,
    ScriptedLLMClient,
)
from .tools import Tool, ToolRegistry

_DEMO_TOOL_NAME = "prepare_demo_artifact"


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "task"


def _build_run_id(task_description: str) -> str:
    return f"{_slugify(task_description)}-{uuid4().hex[:8]}"


def build_demo_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            definition=LLMToolDefinition(
                name=_DEMO_TOOL_NAME,
                description="Prepare deterministic artifact content for a demo task.",
                input_schema={
                    "type": "object",
                    "properties": {"task": {"type": "string"}},
                    "required": ["task"],
                },
            ),
            handler=lambda arguments: {
                "task": arguments["task"],
                "slug": _slugify(arguments["task"]),
                "artifact_body": f"Demo artifact for: {arguments['task']}",
            },
        )
    )
    return registry


def build_demo_llm_client() -> ScriptedLLMClient:
    def first_step(request: LLMRequest) -> LLMResponse:
        payload = json.loads(request.input)
        task_description = payload["task"]["description"]
        selection = request.selection or ModelSelection(provider="demo", model="scripted")
        return LLMResponse(
            text="Planning demo execution via a registered tool.",
            tool_calls=(
                LLMToolCall(
                    id="tool-call-1",
                    name=_DEMO_TOOL_NAME,
                    arguments={"task": task_description},
                ),
            ),
            provider=selection.provider,
            model=selection.model,
        )

    def second_step(request: LLMRequest) -> LLMResponse:
        payload = json.loads(request.input)
        tool_output = payload["tool_results"][0]["output"]
        selection = request.selection or ModelSelection(provider="demo", model="scripted")
        return LLMResponse(
            text=(
                "Demo complete. "
                f"Artifact slug={tool_output['slug']} and summary={tool_output['artifact_body']}"
            ),
            provider=selection.provider,
            model=selection.model,
        )

    return ScriptedLLMClient([first_step, second_step])


async def run_demo_task(
    *,
    task_description: str,
    output_dir: Path,
    selection: ModelSelection | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = _build_run_id(task_description)
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifact_store = ArtifactStore(run_dir / "artifacts")
    event_bus = EventBus(JsonlEventStore(run_dir / "events.jsonl"))
    agent = SingleTaskAgent(
        agent_id="builder-1",
        instructions=(
            "You are TeamAutobot running a minimal single-agent demo. "
            "Use tools when they are available and finish with a concise artifact summary."
        ),
        llm_client=build_demo_llm_client(),
        tool_registry=build_demo_tool_registry(),
        event_bus=event_bus,
        artifact_store=artifact_store,
    )
    task = AgentTask(id=run_id, description=task_description)
    resolved_selection = selection or ModelSelection(provider="demo", model="scripted")
    result = await agent.run_task(task, selection=resolved_selection)
    return {
        "status": "ok",
        "run_dir": str(run_dir),
        "task_id": result.task.id,
        "assistant_text": result.assistant_text,
        "artifact_path": str(result.artifact.path),
        "event_log_path": str(event_bus.path),
        "event_count": result.event_count,
        "tool_names": [tool_result.tool_name for tool_result in result.tool_results],
        "model_selection": {
            "provider": resolved_selection.provider,
            "model": resolved_selection.model,
        },
    }
