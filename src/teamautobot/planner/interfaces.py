from __future__ import annotations

from typing import Protocol

from .models import DependencyHandoff, PlannedTask, TaskExecutionOutput, TaskGraph


class Planner(Protocol):
    def build_plan(self) -> TaskGraph:
        """Build a deterministic task graph."""


class TaskExecutor(Protocol):
    async def execute(
        self,
        task: PlannedTask,
        dependency_handoffs: tuple[DependencyHandoff, ...],
    ) -> TaskExecutionOutput:
        """Execute a single planned task."""
