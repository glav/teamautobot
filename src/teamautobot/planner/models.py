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
class PlannedTask:
    id: str
    description: str
    assignee: str
    order_index: int
    dependencies: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "description": self.description,
            "assignee": self.assignee,
            "order_index": self.order_index,
            "dependencies": list(self.dependencies),
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
    dependencies: tuple[str, ...]
    status: TaskStatus
    artifact_path: str | None = None
    message: str | None = None
    summary: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "order_index": self.order_index,
            "assignee": self.assignee,
            "dependencies": list(self.dependencies),
            "status": self.status.value,
            "artifact_path": self.artifact_path,
            "message": self.message,
            "summary": self.summary,
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
