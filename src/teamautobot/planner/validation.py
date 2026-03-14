from __future__ import annotations

from collections.abc import Mapping

from .models import PlannedTask, TaskGraph, TaskStatus


class TaskGraphValidationError(ValueError):
    """Raised when a task graph violates planner invariants."""


def validate_task_graph(graph: TaskGraph) -> None:
    task_ids: set[str] = set()
    order_indices: set[int] = set()

    for task in graph.tasks:
        if task.id in task_ids:
            raise TaskGraphValidationError(f"Duplicate task id: {task.id}")
        if task.order_index in order_indices:
            raise TaskGraphValidationError(
                f"Duplicate order_index {task.order_index} for task {task.id}"
            )
        if task.order_index < 0:
            raise TaskGraphValidationError(f"order_index must be non-negative for task {task.id}")
        task_ids.add(task.id)
        order_indices.add(task.order_index)

    for task in graph.tasks:
        if task.id in task.dependencies:
            raise TaskGraphValidationError(f"Task {task.id} cannot depend on itself")
        for dependency in task.dependencies:
            if dependency not in task_ids:
                raise TaskGraphValidationError(
                    f"Task {task.id} depends on unknown task {dependency}"
                )

    states: dict[str, str] = {}

    def visit(task_id: str) -> None:
        state = states.get(task_id)
        if state == "visiting":
            raise TaskGraphValidationError(f"Task graph contains a cycle involving {task_id}")
        if state == "visited":
            return

        states[task_id] = "visiting"
        for dependency in graph.task_by_id(task_id).dependencies:
            visit(dependency)
        states[task_id] = "visited"

    for task in graph.tasks:
        visit(task.id)


def ready_tasks(graph: TaskGraph, statuses: Mapping[str, TaskStatus]) -> tuple[PlannedTask, ...]:
    ready: list[PlannedTask] = []
    for task in graph.tasks:
        if statuses.get(task.id, TaskStatus.PENDING) != TaskStatus.PENDING:
            continue
        if all(
            statuses.get(dependency, TaskStatus.PENDING) == TaskStatus.COMPLETED
            for dependency in task.dependencies
        ):
            ready.append(task)
    return tuple(sorted(ready, key=lambda task: task.order_index))


def blocked_dependencies(task: PlannedTask, statuses: Mapping[str, TaskStatus]) -> tuple[str, ...]:
    return tuple(
        dependency
        for dependency in task.dependencies
        if statuses.get(dependency, TaskStatus.PENDING) in {TaskStatus.FAILED, TaskStatus.BLOCKED}
    )
