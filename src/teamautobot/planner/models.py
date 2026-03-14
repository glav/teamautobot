from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

SCHEMA_VERSION = 1
SUMMARY_MAX_LENGTH = 200


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskKind(StrEnum):
    WORK = "work"
    REVIEW = "review"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class DependencyHandoff:
    task_id: str
    artifact_path: str
    summary: str

    def to_dict(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "artifact_path": self.artifact_path,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class ReviewFeedbackItem:
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"message": self.message}

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> ReviewFeedbackItem:
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Review feedback items must include a non-empty message.")
        return cls(message=message)


@dataclass(frozen=True, slots=True)
class ReviewResult:
    subject_task_id: str
    decision: ReviewDecision
    summary: str
    feedback_items: tuple[ReviewFeedbackItem, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_task_id": self.subject_task_id,
            "decision": self.decision.value,
            "summary": self.summary,
            "feedback_items": [item.to_dict() for item in self.feedback_items],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> ReviewResult:
        subject_task_id = payload.get("subject_task_id")
        decision_value = payload.get("decision")
        summary = payload.get("summary")
        feedback_payload = payload.get("feedback_items", [])

        if not isinstance(subject_task_id, str) or not subject_task_id.strip():
            raise ValueError("Review results must include a non-empty subject_task_id.")
        if not isinstance(decision_value, str):
            raise ValueError("Review results must include a string decision.")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Review results must include a non-empty summary.")
        if not isinstance(feedback_payload, list):
            raise ValueError("Review results must include feedback_items as a list.")

        try:
            decision = ReviewDecision(decision_value)
        except ValueError as exc:
            raise ValueError(f"Invalid review decision: {decision_value}") from exc

        feedback_items: list[ReviewFeedbackItem] = []
        for item in feedback_payload:
            if not isinstance(item, dict):
                raise ValueError("Each review feedback item must be an object.")
            feedback_items.append(ReviewFeedbackItem.from_dict(item))

        return cls(
            subject_task_id=subject_task_id,
            decision=decision,
            summary=summary,
            feedback_items=tuple(feedback_items),
        )


@dataclass(frozen=True, slots=True)
class PlannedTask:
    id: str
    description: str
    assignee: str
    order_index: int
    dependencies: tuple[str, ...] = ()
    task_kind: TaskKind = TaskKind.WORK

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "description": self.description,
            "assignee": self.assignee,
            "order_index": self.order_index,
            "dependencies": list(self.dependencies),
            "task_kind": self.task_kind.value,
        }


@dataclass(frozen=True, slots=True)
class TaskGraph:
    scenario_name: str
    tasks: tuple[PlannedTask, ...]

    def ordered_tasks(self) -> tuple[PlannedTask, ...]:
        return tuple(sorted(self.tasks, key=lambda task: task.order_index))

    def task_by_id(self, task_id: str) -> PlannedTask:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise KeyError(task_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_name": self.scenario_name,
            "tasks": [task.to_dict() for task in self.ordered_tasks()],
        }


@dataclass(frozen=True, slots=True)
class PlanSnapshot:
    run_id: str
    scenario_name: str
    tasks: tuple[PlannedTask, ...]
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "scenario_name": self.scenario_name,
            "tasks": [
                task.to_dict() for task in sorted(self.tasks, key=lambda item: item.order_index)
            ],
        }


@dataclass(frozen=True, slots=True)
class TaskRunRecord:
    task_id: str
    order_index: int
    assignee: str
    task_kind: TaskKind
    dependencies: tuple[str, ...]
    status: TaskStatus
    artifact_path: str | None = None
    message: str | None = None
    summary: str | None = None
    review_result: ReviewResult | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "order_index": self.order_index,
            "assignee": self.assignee,
            "task_kind": self.task_kind.value,
            "dependencies": list(self.dependencies),
            "status": self.status.value,
            "artifact_path": self.artifact_path,
            "message": self.message,
            "summary": self.summary,
            "review_result": self.review_result.to_dict() if self.review_result else None,
        }


@dataclass(frozen=True, slots=True)
class ExecutionSummary:
    run_id: str
    scenario_name: str
    task_records: tuple[TaskRunRecord, ...]
    completed_task_ids: tuple[str, ...]
    failed_task_ids: tuple[str, ...]
    blocked_task_ids: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    @property
    def is_success(self) -> bool:
        return not self.failed_task_ids and not self.blocked_task_ids

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "scenario_name": self.scenario_name,
            "completed_task_ids": list(self.completed_task_ids),
            "failed_task_ids": list(self.failed_task_ids),
            "blocked_task_ids": list(self.blocked_task_ids),
            "completed_count": len(self.completed_task_ids),
            "failed_count": len(self.failed_task_ids),
            "blocked_count": len(self.blocked_task_ids),
            "task_records": [record.to_dict() for record in self.task_records],
        }


@dataclass(frozen=True, slots=True)
class TaskExecutionOutput:
    artifact_path: Path
    assistant_text: str
    tool_names: tuple[str, ...] = ()
    review_result: ReviewResult | None = None


@dataclass(frozen=True, slots=True)
class PlannerRunResult:
    run_id: str
    scenario_name: str
    run_dir: Path
    plan_path: Path
    summary_path: Path
    event_log_path: Path
    artifact_paths: tuple[Path, ...]
    summary: ExecutionSummary
