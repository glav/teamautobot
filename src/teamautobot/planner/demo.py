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
from .interfaces import TaskExecutionError, TaskExecutor
from .models import (
    SCHEMA_VERSION,
    DependencyHandoff,
    PlannerRunResult,
    ReviewDecision,
    ReviewResult,
    TaskExecutionOutput,
    TaskKind,
    TaskRunRecord,
)
from .review import validate_review_result
from .runtime import TaskGraphRunner
from .static_planner import ReviewGateStaticPlanner, StaticPlanner

DEFAULT_OUTPUT_DIR = Path(".teamautobot/planner-runs")
_PLANNER_TOOL_NAME = "prepare_planner_task_artifact"
_COLLABORATION_TOOL_NAME = "prepare_collaboration_task_artifact"
_REVIEW_TOOL_NAME = "prepare_review_result"


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


def _build_collaboration_artifact_body(
    task_id: str,
    task: str,
    dependency_handoffs: list[dict[str, str]],
) -> str:
    if task_id == "capture-objective":
        return "Captured the approved objective for the builder-reviewer collaboration demo."

    if task_id == "implement-slice":
        objective_summary = (
            dependency_handoffs[0]["summary"]
            if dependency_handoffs
            else "No objective handoff was available."
        )
        return (
            "Implemented the requested builder slice using the captured objective handoff: "
            f"{objective_summary}"
        )

    if task_id == "publish-summary":
        review_summary = (
            dependency_handoffs[0]["summary"]
            if dependency_handoffs
            else "No review handoff was available."
        )
        return f"Published the collaboration summary after review approval: {review_summary}"

    return _build_artifact_body(task, dependency_handoffs)


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
                name=_PLANNER_TOOL_NAME,
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


def build_review_gate_tool_registry(
    *,
    review_decision: ReviewDecision,
    invalid_review_result: bool = False,
) -> ToolRegistry:
    def prepare_collaboration_artifact(arguments: dict[str, Any]) -> dict[str, Any]:
        dependency_handoffs = list(arguments.get("dependency_handoffs", []))
        return {
            "task_id": arguments["task_id"],
            "slug": _slugify(arguments["task_id"]),
            "artifact_body": _build_collaboration_artifact_body(
                arguments["task_id"],
                arguments["task"],
                dependency_handoffs,
            ),
            "handoff_count": len(dependency_handoffs),
            "handoff_summaries": [handoff["summary"] for handoff in dependency_handoffs],
        }

    def prepare_review_result(arguments: dict[str, Any]) -> dict[str, Any]:
        subject_task_id = arguments["subject_task_id"]
        if invalid_review_result:
            subject_task_id = "capture-objective"
        if review_decision == ReviewDecision.APPROVED:
            summary = "Approved the builder slice for publishing."
            feedback_items: list[dict[str, str]] = []
        else:
            summary = "Rejected the builder slice because it lacks explicit validation evidence."
            feedback_items = [
                {"message": "Add explicit validation evidence before publishing the summary."}
            ]

        return {
            "subject_task_id": subject_task_id,
            "decision": review_decision.value,
            "summary": summary,
            "feedback_items": feedback_items,
            "artifact_body": (
                f"Review {review_decision.value} for {subject_task_id}. "
                f"Subject artifact: {arguments['subject_artifact_path']}. "
                f"{summary}"
            ),
        }

    registry = ToolRegistry()
    registry.register(
        Tool(
            definition=LLMToolDefinition(
                name=_COLLABORATION_TOOL_NAME,
                description="Prepare deterministic artifact content for a collaboration task.",
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
            handler=prepare_collaboration_artifact,
        )
    )
    registry.register(
        Tool(
            definition=LLMToolDefinition(
                name=_REVIEW_TOOL_NAME,
                description="Prepare a deterministic machine-readable review result.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "subject_task_id": {"type": "string"},
                        "subject_artifact_path": {"type": "string"},
                        "subject_summary": {"type": "string"},
                    },
                    "required": [
                        "subject_task_id",
                        "subject_artifact_path",
                        "subject_summary",
                    ],
                },
            ),
            handler=prepare_review_result,
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
                    name=_PLANNER_TOOL_NAME,
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


def build_review_gate_llm_client(
    *,
    review_decision: ReviewDecision,
    fail_task_id: str | None = None,
) -> ScriptedLLMClient:
    def first_step(request: LLMRequest) -> LLMResponse | LLMError:
        payload = json.loads(request.input)
        task_payload = payload["task"]
        selection = request.selection or ModelSelection(provider="demo", model="scripted")
        if task_payload["id"] == fail_task_id:
            return LLMError(
                kind=LLMErrorKind.TRANSIENT,
                message=f"Simulated review demo failure for task {task_payload['id']}",
                provider=selection.provider,
            )

        dependency_handoffs = task_payload.get("context", {}).get("dependency_handoffs", [])
        if task_payload.get("context", {}).get("task_kind") == TaskKind.REVIEW.value:
            subject_handoff = dependency_handoffs[0]
            return LLMResponse(
                text="Preparing deterministic review output via a tool.",
                tool_calls=(
                    LLMToolCall(
                        id="review-tool-call-1",
                        name=_REVIEW_TOOL_NAME,
                        arguments={
                            "subject_task_id": subject_handoff["task_id"],
                            "subject_artifact_path": subject_handoff["artifact_path"],
                            "subject_summary": subject_handoff["summary"],
                        },
                    ),
                ),
                provider=selection.provider,
                model=selection.model,
            )

        return LLMResponse(
            text="Preparing collaboration task output via a deterministic tool.",
            tool_calls=(
                LLMToolCall(
                    id="collaboration-tool-call-1",
                    name=_COLLABORATION_TOOL_NAME,
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

        if task_payload.get("context", {}).get("task_kind") == TaskKind.REVIEW.value:
            return LLMResponse(
                text=f"Review complete. {tool_output['summary']}",
                provider=selection.provider,
                model=selection.model,
            )

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
                    "task_kind": task.task_kind.value,
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


class ReviewGateDemoTaskExecutor(TaskExecutor):
    def __init__(
        self,
        *,
        event_bus: EventBus,
        artifact_store: ArtifactStore,
        selection: ModelSelection | None = None,
        review_decision: ReviewDecision = ReviewDecision.APPROVED,
        fail_task_id: str | None = None,
        invalid_review_result: bool = False,
    ) -> None:
        self._event_bus = event_bus
        self._artifact_store = artifact_store
        self._selection = selection or ModelSelection(provider="demo", model="scripted")
        self._review_decision = review_decision
        self._fail_task_id = fail_task_id
        self._invalid_review_result = invalid_review_result

    async def execute(
        self,
        task,
        dependency_handoffs: tuple[DependencyHandoff, ...],
    ) -> TaskExecutionOutput:
        agent = SingleTaskAgent(
            agent_id=task.assignee,
            instructions=(
                "You are TeamAutobot running a deterministic collaboration demo task. "
                "Use tools when available and produce a concise artifact summary."
            ),
            llm_client=build_review_gate_llm_client(
                review_decision=self._review_decision,
                fail_task_id=self._fail_task_id,
            ),
            tool_registry=build_review_gate_tool_registry(
                review_decision=self._review_decision,
                invalid_review_result=self._invalid_review_result,
            ),
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
                    "task_kind": task.task_kind.value,
                    "dependency_handoffs": [handoff.to_dict() for handoff in dependency_handoffs],
                },
            ),
            selection=self._selection,
            emit_completion_event=task.task_kind != TaskKind.REVIEW,
        )

        review_result = None
        if task.task_kind == TaskKind.REVIEW:
            try:
                if not result.tool_results or not isinstance(result.tool_results[0].output, dict):
                    raise TaskExecutionError(
                        f"Review task {task.id} completed without a structured review result.",
                        error_kind="review_contract",
                        artifact_path=result.artifact.path,
                    )
                review_result = ReviewResult.from_dict(result.tool_results[0].output)
                review_result = validate_review_result(
                    task_id=task.id,
                    dependency_handoffs=dependency_handoffs,
                    review_result=review_result,
                )
            except ValueError as exc:
                raise TaskExecutionError(
                    str(exc),
                    error_kind="review_contract",
                    artifact_path=result.artifact.path,
                ) from exc
            self._event_bus.emit(
                "task.completed",
                source=task.assignee,
                correlation_id=task.id,
                payload={"task_id": task.id, "artifact_path": str(result.artifact.path)},
            )

        return TaskExecutionOutput(
            artifact_path=result.artifact.path,
            assistant_text=result.assistant_text,
            tool_names=tuple(tool_result.tool_name for tool_result in result.tool_results),
            review_result=review_result,
        )


def _base_payload(result: PlannerRunResult) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
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


def _build_success_payload(result: PlannerRunResult) -> dict[str, Any]:
    return {
        **_base_payload(result),
        "status": "ok",
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
        "message": (
            f"Planner demo finished with {failed_count} failed task(s) "
            f"and {blocked_count} blocked task(s)."
        ),
        "failed_task_ids": list(result.summary.failed_task_ids),
        "blocked_task_ids": list(result.summary.blocked_task_ids),
    }


def _find_review_record(result: PlannerRunResult) -> TaskRunRecord | None:
    for record in result.summary.task_records:
        if record.review_result is not None:
            return record
    return None


def _build_review_success_payload(
    result: PlannerRunResult, review_record: TaskRunRecord
) -> dict[str, Any]:
    assert review_record.review_result is not None
    return {
        **_base_payload(result),
        "status": "ok",
        "review_status": review_record.review_result.decision.value,
        "review_task_id": review_record.task_id,
        "reviewed_task_id": review_record.review_result.subject_task_id,
        "review_artifact_path": review_record.artifact_path,
        "feedback_count": len(review_record.review_result.feedback_items),
    }


def _build_review_rejection_payload(
    result: PlannerRunResult, review_record: TaskRunRecord
) -> dict[str, Any]:
    assert review_record.review_result is not None
    return {
        **_base_payload(result),
        "status": "error",
        "message": (
            f"Review demo finished with a rejected review and "
            f"{len(result.summary.blocked_task_ids)} blocked task(s)."
        ),
        "review_status": review_record.review_result.decision.value,
        "review_task_id": review_record.task_id,
        "reviewed_task_id": review_record.review_result.subject_task_id,
        "review_artifact_path": review_record.artifact_path,
        "feedback_count": len(review_record.review_result.feedback_items),
    }


def _build_review_demo_payload(result: PlannerRunResult) -> dict[str, Any]:
    if result.summary.failed_task_ids:
        return _build_failure_payload(result)

    review_record = _find_review_record(result)
    if review_record is None or review_record.review_result is None:
        return _build_failure_payload(result)

    if review_record.review_result.decision == ReviewDecision.APPROVED:
        return _build_review_success_payload(result, review_record)

    return _build_review_rejection_payload(result, review_record)


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


async def run_review_demo(
    *,
    output_dir: Path,
    selection: ModelSelection | None = None,
    review_decision: ReviewDecision = ReviewDecision.APPROVED,
    fail_task_id: str | None = None,
    invalid_review_result: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    planner = ReviewGateStaticPlanner()
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
        task_executor=ReviewGateDemoTaskExecutor(
            event_bus=event_bus,
            artifact_store=task_artifact_store,
            selection=selection,
            review_decision=review_decision,
            fail_task_id=fail_task_id,
            invalid_review_result=invalid_review_result,
        ),
    )
    result = await runner.run(graph, run_id=run_id)
    return _build_review_demo_payload(result)
