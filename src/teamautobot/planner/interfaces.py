from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import DependencyHandoff, PlannedTask, TaskExecutionOutput, TaskGraph


class Planner(Protocol):
    def build_plan(self) -> TaskGraph:
        """Build a deterministic task graph."""


class TaskExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_kind: str = "task_execution",
        artifact_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.error_kind = error_kind
        self.artifact_path = artifact_path


class TaskExecutor(Protocol):
    async def execute(
        self,
        task: PlannedTask,
        dependency_handoffs: tuple[DependencyHandoff, ...],
    ) -> TaskExecutionOutput:
        """Execute a single planned task."""
