from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..agents import AgentRunError
from ..artifacts import ArtifactStore
from ..events import EventBus
from .interfaces import TaskExecutor
from .models import (
    SUMMARY_MAX_LENGTH,
    DependencyHandoff,
    ExecutionSummary,
    PlannerRunResult,
    PlanSnapshot,
    TaskGraph,
    TaskRunRecord,
    TaskStatus,
)
from .validation import blocked_dependencies, ready_tasks, validate_task_graph


class PlannerRuntimeError(RuntimeError):
    """Raised when the planner runtime encounters an unrecoverable state."""


def normalize_summary(text: str, *, limit: int = SUMMARY_MAX_LENGTH) -> str:
    normalized = " ".join(text.split()) or "No summary available."
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


class TaskGraphRunner:
    def __init__(
        self,
        *,
        run_dir: Path,
        planner_artifact_store: ArtifactStore,
        task_artifact_store: ArtifactStore,
        event_bus: EventBus,
        task_executor: TaskExecutor,
    ) -> None:
        self._run_dir = run_dir
        self._planner_artifact_store = planner_artifact_store
        self._task_artifact_store = task_artifact_store
        self._event_bus = event_bus
        self._task_executor = task_executor

    async def run(self, graph: TaskGraph, *, run_id: str) -> PlannerRunResult:
        validate_task_graph(graph)

        plan_snapshot = PlanSnapshot(
            run_id=run_id,
            scenario_name=graph.scenario_name,
            tasks=graph.tasks,
        )
        plan_artifact = self._planner_artifact_store.write_json("plan", plan_snapshot.to_dict())

        records: dict[str, TaskRunRecord] = {
            task.id: TaskRunRecord(
                task_id=task.id,
                order_index=task.order_index,
                assignee=task.assignee,
                dependencies=task.dependencies,
                status=TaskStatus.PENDING,
            )
            for task in graph.ordered_tasks()
        }
        handoffs: dict[str, DependencyHandoff] = {}

        for task in graph.ordered_tasks():
            self._event_bus.emit(
                "task.assigned",
                source="planner",
                target=task.assignee,
                correlation_id=task.id,
                payload={
                    "task_id": task.id,
                    "assignee": task.assignee,
                    "dependencies": list(task.dependencies),
                },
            )

        while True:
            self._mark_blocked_tasks(graph, records)
            status_map = {task_id: record.status for task_id, record in records.items()}
            ready = ready_tasks(graph, status_map)

            if not ready:
                if any(record.status == TaskStatus.PENDING for record in records.values()):
                    message = "No ready tasks remained while pending tasks still existed."
                    self._event_bus.emit(
                        "system.error",
                        source="planner",
                        correlation_id=run_id,
                        payload={"kind": "runtime", "message": message},
                    )
                    raise PlannerRuntimeError(message)
                break

            task = ready[0]
            records[task.id] = replace(records[task.id], status=TaskStatus.RUNNING)
            dependency_handoffs = tuple(
                handoffs[dependency] for dependency in task.dependencies if dependency in handoffs
            )

            try:
                result = await self._task_executor.execute(task, dependency_handoffs)
            except AgentRunError as exc:
                records[task.id] = replace(
                    records[task.id],
                    status=TaskStatus.FAILED,
                    message=exc.error.message,
                )
                self._event_bus.emit(
                    "task.failed",
                    source="planner",
                    correlation_id=task.id,
                    payload={"task_id": task.id, "message": exc.error.message},
                )
                continue
            except Exception as exc:  # pragma: no cover - defensive branch
                message = str(exc)
                self._event_bus.emit(
                    "system.error",
                    source="planner",
                    correlation_id=task.id,
                    payload={"task_id": task.id, "kind": "unexpected", "message": message},
                )
                records[task.id] = replace(
                    records[task.id],
                    status=TaskStatus.FAILED,
                    message=message,
                )
                self._event_bus.emit(
                    "task.failed",
                    source="planner",
                    correlation_id=task.id,
                    payload={"task_id": task.id, "message": message},
                )
                continue

            summary = normalize_summary(result.assistant_text)
            records[task.id] = replace(
                records[task.id],
                status=TaskStatus.COMPLETED,
                artifact_path=str(result.artifact_path),
                summary=summary,
            )
            handoffs[task.id] = DependencyHandoff(
                task_id=task.id,
                artifact_path=str(result.artifact_path),
                summary=summary,
            )

        summary = ExecutionSummary(
            run_id=run_id,
            scenario_name=graph.scenario_name,
            task_records=tuple(records[task.id] for task in graph.ordered_tasks()),
            completed_task_ids=tuple(
                task.id
                for task in graph.ordered_tasks()
                if records[task.id].status == TaskStatus.COMPLETED
            ),
            failed_task_ids=tuple(
                task.id
                for task in graph.ordered_tasks()
                if records[task.id].status == TaskStatus.FAILED
            ),
            blocked_task_ids=tuple(
                task.id
                for task in graph.ordered_tasks()
                if records[task.id].status == TaskStatus.BLOCKED
            ),
        )
        summary_artifact = self._planner_artifact_store.write_json(
            "execution-summary", summary.to_dict()
        )
        self._event_bus.emit(
            "system.complete",
            source="planner",
            correlation_id=run_id,
            payload={
                "run_id": run_id,
                "completed_task_ids": list(summary.completed_task_ids),
                "failed_task_ids": list(summary.failed_task_ids),
                "blocked_task_ids": list(summary.blocked_task_ids),
            },
        )

        artifact_paths = tuple(
            Path(record.artifact_path)
            for task in graph.ordered_tasks()
            if (record := records[task.id]).artifact_path is not None
        )
        return PlannerRunResult(
            run_id=run_id,
            scenario_name=graph.scenario_name,
            run_dir=self._run_dir,
            plan_path=plan_artifact.path,
            summary_path=summary_artifact.path,
            event_log_path=self._event_bus.path,
            artifact_paths=artifact_paths,
            summary=summary,
        )

    def _mark_blocked_tasks(self, graph: TaskGraph, records: dict[str, TaskRunRecord]) -> None:
        status_map = {task_id: record.status for task_id, record in records.items()}
        for task in graph.ordered_tasks():
            record = records[task.id]
            if record.status != TaskStatus.PENDING:
                continue

            blocked_by = blocked_dependencies(task, status_map)
            if not blocked_by:
                continue

            records[task.id] = replace(
                record,
                status=TaskStatus.BLOCKED,
                message=f"Blocked by failed dependencies: {', '.join(blocked_by)}",
            )
            self._event_bus.emit(
                "task.blocked",
                source="planner",
                correlation_id=task.id,
                payload={"task_id": task.id, "blocked_by": list(blocked_by)},
            )
