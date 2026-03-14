"""Planner package for the TeamAutobot planner and collaboration demo slices."""

from .demo import DEFAULT_OUTPUT_DIR, run_planner_demo, run_review_demo
from .interfaces import Planner, TaskExecutionError, TaskExecutor
from .models import (
    SCHEMA_VERSION,
    SUMMARY_MAX_LENGTH,
    DependencyHandoff,
    ExecutionSummary,
    PlannedTask,
    PlannerRunResult,
    PlanSnapshot,
    ReviewDecision,
    ReviewFeedbackItem,
    ReviewResult,
    TaskExecutionOutput,
    TaskGraph,
    TaskKind,
    TaskRunRecord,
    TaskStatus,
)
from .review import ReviewContractError, resolve_review_subject, validate_review_result
from .runtime import PlannerRuntimeError, TaskGraphRunner, normalize_summary
from .static_planner import (
    DEMO_SCENARIO_NAME,
    REVIEW_DEMO_SCENARIO_NAME,
    ReviewGateStaticPlanner,
    StaticPlanner,
)
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
    "ReviewContractError",
    "ReviewDecision",
    "ReviewFeedbackItem",
    "ReviewGateStaticPlanner",
    "ReviewResult",
    "REVIEW_DEMO_SCENARIO_NAME",
    "SCHEMA_VERSION",
    "SUMMARY_MAX_LENGTH",
    "StaticPlanner",
    "TaskExecutionOutput",
    "TaskExecutionError",
    "TaskExecutor",
    "TaskGraph",
    "TaskGraphRunner",
    "TaskGraphValidationError",
    "TaskKind",
    "TaskRunRecord",
    "TaskStatus",
    "blocked_dependencies",
    "normalize_summary",
    "ready_tasks",
    "run_planner_demo",
    "run_review_demo",
    "resolve_review_subject",
    "validate_review_result",
    "validate_task_graph",
]
