"""Planner package for the first TeamAutobot task-graph slice."""

from .demo import DEFAULT_OUTPUT_DIR, run_planner_demo
from .interfaces import Planner, TaskExecutor
from .models import (
    SCHEMA_VERSION,
    SUMMARY_MAX_LENGTH,
    DependencyHandoff,
    ExecutionSummary,
    PlannedTask,
    PlannerRunResult,
    PlanSnapshot,
    TaskExecutionOutput,
    TaskGraph,
    TaskRunRecord,
    TaskStatus,
)
from .runtime import PlannerRuntimeError, TaskGraphRunner, normalize_summary
from .static_planner import DEMO_SCENARIO_NAME, StaticPlanner
from .validation import (
    TaskGraphValidationError,
    blocked_dependencies,
    ready_tasks,
    validate_task_graph,
)

__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "DEMO_SCENARIO_NAME",
    "DependencyHandoff",
    "ExecutionSummary",
    "Planner",
    "PlannerRunResult",
    "PlanSnapshot",
    "PlannedTask",
    "PlannerRuntimeError",
    "SCHEMA_VERSION",
    "SUMMARY_MAX_LENGTH",
    "StaticPlanner",
    "TaskExecutionOutput",
    "TaskExecutor",
    "TaskGraph",
    "TaskGraphRunner",
    "TaskGraphValidationError",
    "TaskRunRecord",
    "TaskStatus",
    "blocked_dependencies",
    "normalize_summary",
    "ready_tasks",
    "run_planner_demo",
    "validate_task_graph",
]
