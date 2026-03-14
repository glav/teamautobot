from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..agents import AgentRunError
from ..artifacts import ArtifactStore
from ..events import EventBus
from .interfaces import TaskExecutionError, TaskExecutor
from .models import (
    SUMMARY_MAX_LENGTH,
    DependencyHandoff,
    ExecutionSummary,
    PlannerRunResult,
    PlanSnapshot,
    ReviewDecision,
    ReviewResult,
    TaskGraph,
    TaskKind,
    TaskRunRecord,
    TaskStatus,
)
from .review import ReviewContractError, resolve_review_subject
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
                task_kind=task.task_kind,
                dependencies=task.dependencies,
                status=TaskStatus.PENDING,
            )
            for task in graph.ordered_tasks()
        }
        handoffs: dict[str, DependencyHandoff] = {}
        rejected_review_task_ids: set[str] = set()

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
                    "task_kind": task.task_kind.value,
                },
            )

        while True:
            self._mark_blocked_tasks(
                graph,
                records,
                rejected_review_task_ids=rejected_review_task_ids,
            )
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

            if task.task_kind == TaskKind.REVIEW:
                try:
                    subject_handoff = resolve_review_subject(
                        task_id=task.id,
                        dependency_handoffs=dependency_handoffs,
                    )
                except ReviewContractError as exc:
                    self._record_task_failure(
                        records,
                        task_id=task.id,
                        message=str(exc),
                        error_kind="review_contract",
                    )
                    continue
                self._emit_review_requested(
                    review_task_id=task.id,
                    reviewer_id=task.assignee,
                    subject_handoff=subject_handoff,
                )

            try:
                result = await self._task_executor.execute(task, dependency_handoffs)
            except TaskExecutionError as exc:
                self._record_task_failure(
                    records,
                    task_id=task.id,
                    message=str(exc),
                    error_kind=exc.error_kind,
                    artifact_path=exc.artifact_path,
                )
                continue
            except AgentRunError as exc:
                self._record_task_failure(records, task_id=task.id, message=exc.error.message)
                continue
            except Exception as exc:  # pragma: no cover - defensive branch
                self._record_task_failure(
                    records,
                    task_id=task.id,
                    message=str(exc),
                    error_kind="unexpected",
                )
                continue

            summary = normalize_summary(result.assistant_text)
            review_result = result.review_result
            if task.task_kind == TaskKind.REVIEW and review_result is None:
                self._record_task_failure(
                    records,
                    task_id=task.id,
                    message=f"Review task {task.id} completed without a review result.",
                    error_kind="review_contract",
                    artifact_path=result.artifact_path,
                )
                continue

            records[task.id] = replace(
                records[task.id],
                status=TaskStatus.COMPLETED,
                artifact_path=str(result.artifact_path),
                summary=summary,
                review_result=review_result,
            )
            handoffs[task.id] = DependencyHandoff(
                task_id=task.id,
                artifact_path=str(result.artifact_path),
                summary=summary,
            )
            if review_result is not None:
                self._emit_review_outcome(
                    graph=graph,
                    review_task_id=task.id,
                    reviewer_id=task.assignee,
                    artifact_path=result.artifact_path,
                    review_result=review_result,
                )
                if review_result.decision == ReviewDecision.REJECTED:
                    rejected_review_task_ids.add(task.id)

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

    def _record_task_failure(
        self,
        records: dict[str, TaskRunRecord],
        *,
        task_id: str,
        message: str,
        error_kind: str | None = None,
        artifact_path: Path | None = None,
    ) -> None:
        if error_kind is not None:
            self._event_bus.emit(
                "system.error",
                source="planner",
                correlation_id=task_id,
                payload={"task_id": task_id, "kind": error_kind, "message": message},
            )
        records[task_id] = replace(
            records[task_id],
            status=TaskStatus.FAILED,
            message=message,
            artifact_path=str(artifact_path) if artifact_path is not None else None,
        )
        self._event_bus.emit(
            "task.failed",
            source="planner",
            correlation_id=task_id,
            payload={"task_id": task_id, "message": message},
        )

    def _emit_review_requested(
        self,
        *,
        review_task_id: str,
        reviewer_id: str,
        subject_handoff: DependencyHandoff,
    ) -> None:
        self._event_bus.emit(
            "review.requested",
            source="planner",
            target=reviewer_id,
            correlation_id=review_task_id,
            payload={
                "review_task_id": review_task_id,
                "subject_task_id": subject_handoff.task_id,
                "subject_artifact_path": subject_handoff.artifact_path,
            },
        )

    def _emit_review_outcome(
        self,
        *,
        graph: TaskGraph,
        review_task_id: str,
        reviewer_id: str,
        artifact_path: Path,
        review_result: ReviewResult,
    ) -> None:
        subject_task = graph.task_by_id(review_result.subject_task_id)
        shared_payload = {
            "review_task_id": review_task_id,
            "subject_task_id": review_result.subject_task_id,
            "review_artifact_path": str(artifact_path),
        }
        feedback_items = [item.to_dict() for item in review_result.feedback_items]

        self._event_bus.emit(
            "review.feedback",
            source=reviewer_id,
            target=subject_task.assignee,
            correlation_id=review_task_id,
            payload={
                **shared_payload,
                "decision": review_result.decision.value,
                "feedback_items": feedback_items,
            },
        )

        if review_result.decision == ReviewDecision.APPROVED:
            self._event_bus.emit(
                "review.approved",
                source=reviewer_id,
                target=subject_task.assignee,
                correlation_id=review_task_id,
                payload=shared_payload,
            )
            return

        self._event_bus.emit(
            "review.rejected",
            source=reviewer_id,
            target=subject_task.assignee,
            correlation_id=review_task_id,
            payload={**shared_payload, "feedback_items": feedback_items},
        )

    def _mark_blocked_tasks(
        self,
        graph: TaskGraph,
        records: dict[str, TaskRunRecord],
        *,
        rejected_review_task_ids: set[str],
    ) -> None:
        status_map = {task_id: record.status for task_id, record in records.items()}
        for task in graph.ordered_tasks():
            record = records[task.id]
            if record.status != TaskStatus.PENDING:
                continue

            blocked_by = list(blocked_dependencies(task, status_map))
            rejected_by = [
                dependency
                for dependency in task.dependencies
                if dependency in rejected_review_task_ids
            ]
            blockers = list(dict.fromkeys(blocked_by + rejected_by))
            if not blockers:
                continue

            if rejected_by and not blocked_by:
                message = f"Blocked by rejected review dependencies: {', '.join(blockers)}"
            elif blocked_by and not rejected_by:
                message = f"Blocked by failed dependencies: {', '.join(blockers)}"
            else:
                message = f"Blocked by failed or rejected dependencies: {', '.join(blockers)}"

            records[task.id] = replace(
                record,
                status=TaskStatus.BLOCKED,
                message=message,
            )
            self._event_bus.emit(
                "task.blocked",
                source="planner",
                correlation_id=task.id,
                payload={"task_id": task.id, "blocked_by": blockers},
            )
