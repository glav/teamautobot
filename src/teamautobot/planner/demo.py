from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..agents import AgentTask, SingleTaskAgent
from ..artifacts import ArtifactStore
from ..events import EventBus, JsonlEventStore
from ..llm import (
    LLMError,
    LLMErrorKind,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    ModelSelection,
    ScriptedLLMClient,
)
from ..tools import Tool, ToolRegistry
from .interfaces import TaskExecutor
from .models import (
    SCHEMA_VERSION,
    DependencyHandoff,
    PlannerRunResult,
    TaskExecutionOutput,
)
from .runtime import TaskGraphRunner
from .static_planner import StaticPlanner

DEFAULT_OUTPUT_DIR = Path(".teamautobot/planner-runs")
_DEMO_TOOL_NAME = "prepare_planner_task_artifact"


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "task"


def _build_run_id(scenario_name: str) -> str:
    return f"{_slugify(scenario_name)}-{uuid4().hex[:8]}"


def _build_artifact_body(task: str, dependency_handoffs: list[dict[str, str]]) -> str:
    if not dependency_handoffs:
        return f"Planner artifact for: {task}. No dependency handoffs were required."

    handoff_summaries = "; ".join(
        f"{handoff['task_id']}={handoff['summary']}" for handoff in dependency_handoffs
    )
    return f"Planner artifact for: {task}. Dependency handoffs: {handoff_summaries}"


def build_planner_demo_tool_registry() -> ToolRegistry:
    def prepare_planner_artifact(arguments: dict[str, Any]) -> dict[str, Any]:
        dependency_handoffs = list(arguments.get("dependency_handoffs", []))
        return {
            "task_id": arguments["task_id"],
            "slug": _slugify(arguments["task_id"]),
            "artifact_body": _build_artifact_body(arguments["task"], dependency_handoffs),
            "handoff_count": len(dependency_handoffs),
            "handoff_summaries": [handoff["summary"] for handoff in dependency_handoffs],
        }

    registry = ToolRegistry()
    registry.register(
        Tool(
            definition=LLMToolDefinition(
                name=_DEMO_TOOL_NAME,
                description="Prepare deterministic artifact content for a planner task.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "task": {"type": "string"},
                        "dependency_handoffs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "task_id": {"type": "string"},
                                    "artifact_path": {"type": "string"},
                                    "summary": {"type": "string"},
                                },
                                "required": ["task_id", "artifact_path", "summary"],
                            },
                        },
                    },
                    "required": ["task_id", "task", "dependency_handoffs"],
                },
            ),
            handler=prepare_planner_artifact,
        )
    )
    return registry


def build_planner_demo_llm_client(*, fail_task_id: str | None = None) -> ScriptedLLMClient:
    def first_step(request: LLMRequest) -> LLMResponse | LLMError:
        payload = json.loads(request.input)
        task_payload = payload["task"]
        selection = request.selection or ModelSelection(provider="demo", model="scripted")
        if task_payload["id"] == fail_task_id:
            return LLMError(
                kind=LLMErrorKind.TRANSIENT,
                message=f"Simulated planner demo failure for task {task_payload['id']}",
                provider=selection.provider,
            )

        dependency_handoffs = task_payload.get("context", {}).get("dependency_handoffs", [])
        return LLMResponse(
            text="Preparing planner task output via a deterministic tool.",
            tool_calls=(
                LLMToolCall(
                    id="planner-tool-call-1",
                    name=_DEMO_TOOL_NAME,
                    arguments={
                        "task_id": task_payload["id"],
                        "task": task_payload["description"],
                        "dependency_handoffs": dependency_handoffs,
                    },
                ),
            ),
            provider=selection.provider,
            model=selection.model,
        )

    def second_step(request: LLMRequest) -> LLMResponse:
        payload = json.loads(request.input)
        task_payload = payload["task"]
        tool_output = payload["tool_results"][0]["output"]
        selection = request.selection or ModelSelection(provider="demo", model="scripted")
        return LLMResponse(
            text=f"{task_payload['description']} complete. {tool_output['artifact_body']}",
            provider=selection.provider,
            model=selection.model,
        )

    return ScriptedLLMClient([first_step, second_step])


class PlannerDemoTaskExecutor(TaskExecutor):
    def __init__(
        self,
        *,
        event_bus: EventBus,
        artifact_store: ArtifactStore,
        selection: ModelSelection | None = None,
        fail_task_id: str | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._artifact_store = artifact_store
        self._selection = selection or ModelSelection(provider="demo", model="scripted")
        self._fail_task_id = fail_task_id

    async def execute(
        self,
        task,
        dependency_handoffs: tuple[DependencyHandoff, ...],
    ) -> TaskExecutionOutput:
        agent = SingleTaskAgent(
            agent_id=task.assignee,
            instructions=(
                "You are TeamAutobot running a deterministic planner demo task. "
                "Use tools when available and produce a concise artifact summary."
            ),
            llm_client=build_planner_demo_llm_client(fail_task_id=self._fail_task_id),
            tool_registry=build_planner_demo_tool_registry(),
            event_bus=self._event_bus,
            artifact_store=self._artifact_store,
        )
        result = await agent.run_task(
            AgentTask(
                id=task.id,
                description=task.description,
                context={
                    "assignee": task.assignee,
                    "order_index": task.order_index,
                    "dependency_handoffs": [handoff.to_dict() for handoff in dependency_handoffs],
                },
            ),
            selection=self._selection,
        )
        return TaskExecutionOutput(
            artifact_path=result.artifact.path,
            assistant_text=result.assistant_text,
            tool_names=tuple(tool_result.tool_name for tool_result in result.tool_results),
        )


def _build_success_payload(result: PlannerRunResult) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "scenario_name": result.scenario_name,
        "run_dir": str(result.run_dir),
        "plan_path": str(result.plan_path),
        "summary_path": str(result.summary_path),
        "event_log_path": str(result.event_log_path),
        "artifact_paths": [str(path) for path in result.artifact_paths],
        "completed_task_ids": list(result.summary.completed_task_ids),
        "failed_task_ids": list(result.summary.failed_task_ids),
        "blocked_task_ids": list(result.summary.blocked_task_ids),
    }


def _build_failure_payload(result: PlannerRunResult) -> dict[str, Any]:
    failed_count = len(result.summary.failed_task_ids)
    blocked_count = len(result.summary.blocked_task_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "error",
        "scenario_name": result.scenario_name,
        "run_dir": str(result.run_dir),
        "plan_path": str(result.plan_path),
        "summary_path": str(result.summary_path),
        "event_log_path": str(result.event_log_path),
        "failed_task_ids": list(result.summary.failed_task_ids),
        "blocked_task_ids": list(result.summary.blocked_task_ids),
        "message": (
            f"Planner demo finished with {failed_count} failed task(s) "
            f"and {blocked_count} blocked task(s)."
        ),
    }


async def run_planner_demo(
    *,
    output_dir: Path,
    selection: ModelSelection | None = None,
    fail_task_id: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    planner = StaticPlanner()
    graph = planner.build_plan()
    run_id = _build_run_id(graph.scenario_name)
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    event_bus = EventBus(JsonlEventStore(run_dir / "events.jsonl"))
    planner_artifact_store = ArtifactStore(run_dir / "artifacts" / "planner")
    task_artifact_store = ArtifactStore(run_dir / "artifacts" / "tasks")
    runner = TaskGraphRunner(
        run_dir=run_dir,
        planner_artifact_store=planner_artifact_store,
        task_artifact_store=task_artifact_store,
        event_bus=event_bus,
        task_executor=PlannerDemoTaskExecutor(
            event_bus=event_bus,
            artifact_store=task_artifact_store,
            selection=selection,
            fail_task_id=fail_task_id,
        ),
    )
    result = await runner.run(graph, run_id=run_id)
    if result.summary.is_success:
        return _build_success_payload(result)
    return _build_failure_payload(result)
