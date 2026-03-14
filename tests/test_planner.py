from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from teamautobot.artifacts import ArtifactStore
from teamautobot.events import EventBus, JsonlEventStore
from teamautobot.planner import (
    SCHEMA_VERSION,
    PlannedTask,
    TaskExecutionOutput,
    TaskGraph,
    TaskGraphRunner,
    TaskGraphValidationError,
    ready_tasks,
    validate_task_graph,
)
from teamautobot.planner.demo import run_planner_demo


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_events(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_validate_task_graph_rejects_duplicate_order_index() -> None:
    graph = TaskGraph(
        scenario_name="duplicate-order-index",
        tasks=(
            PlannedTask(
                id="capture-objective",
                description="Capture the objective.",
                assignee="ba",
                order_index=1,
            ),
            PlannedTask(
                id="draft-work-breakdown",
                description="Draft the work breakdown.",
                assignee="pm",
                order_index=1,
            ),
        ),
    )

    with pytest.raises(TaskGraphValidationError, match="Duplicate order_index"):
        validate_task_graph(graph)


def test_validate_task_graph_rejects_cycles() -> None:
    graph = TaskGraph(
        scenario_name="cyclic-graph",
        tasks=(
            PlannedTask(
                id="capture-objective",
                description="Capture the objective.",
                assignee="ba",
                order_index=1,
                dependencies=("publish-summary",),
            ),
            PlannedTask(
                id="publish-summary",
                description="Publish the summary.",
                assignee="writer",
                order_index=2,
                dependencies=("capture-objective",),
            ),
        ),
    )

    with pytest.raises(TaskGraphValidationError, match="cycle"):
        validate_task_graph(graph)


def test_ready_tasks_use_order_index_instead_of_tuple_position() -> None:
    graph = TaskGraph(
        scenario_name="out-of-order",
        tasks=(
            PlannedTask(
                id="draft-work-breakdown",
                description="Draft the work breakdown.",
                assignee="pm",
                order_index=2,
            ),
            PlannedTask(
                id="capture-objective",
                description="Capture the objective.",
                assignee="ba",
                order_index=1,
            ),
        ),
    )

    validate_task_graph(graph)

    assert [task.id for task in ready_tasks(graph, {})] == [
        "capture-objective",
        "draft-work-breakdown",
    ]


def test_run_planner_demo_writes_versioned_artifacts_and_handoffs(
    tmp_path: Path,
) -> None:
    payload = asyncio.run(run_planner_demo(output_dir=tmp_path))

    assert payload["status"] == "ok"
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["completed_task_ids"] == [
        "capture-objective",
        "draft-work-breakdown",
        "draft-validation-checklist",
        "publish-summary",
    ]
    assert payload["failed_task_ids"] == []
    assert payload["blocked_task_ids"] == []

    run_dir = Path(str(payload["run_dir"]))
    plan_path = Path(str(payload["plan_path"]))
    summary_path = Path(str(payload["summary_path"]))
    event_log_path = Path(str(payload["event_log_path"]))
    artifact_paths = [Path(path) for path in payload["artifact_paths"]]

    assert run_dir.exists()
    assert plan_path.exists()
    assert summary_path.exists()
    assert event_log_path.exists()
    assert [path.name for path in artifact_paths] == [
        "capture-objective.json",
        "draft-work-breakdown.json",
        "draft-validation-checklist.json",
        "publish-summary.json",
    ]

    plan_payload = _read_json(plan_path)
    summary_payload = _read_json(summary_path)
    draft_breakdown_payload = _read_json(
        run_dir / "artifacts" / "tasks" / "draft-work-breakdown.json"
    )
    events = _read_events(event_log_path)

    assert plan_payload["schema_version"] == SCHEMA_VERSION
    assert summary_payload["schema_version"] == SCHEMA_VERSION
    assert [task["order_index"] for task in plan_payload["tasks"]] == [1, 2, 3, 4]
    assert summary_payload["completed_count"] == 4
    assert summary_payload["failed_count"] == 0
    assert summary_payload["blocked_count"] == 0

    handoffs = draft_breakdown_payload["task"]["context"]["dependency_handoffs"]
    assert len(handoffs) == 1
    assert handoffs[0]["task_id"] == "capture-objective"
    assert Path(handoffs[0]["artifact_path"]).name == "capture-objective.json"
    assert len(handoffs[0]["summary"]) <= 200
    assert "\n" not in handoffs[0]["summary"]

    assert [event["type"] for event in events[:4]] == ["task.assigned"] * 4
    assert [event["target"] for event in events[:4]] == [
        "ba",
        "pm",
        "reviewer",
        "writer",
    ]
    assert events[-1]["type"] == "system.complete"


def test_run_planner_demo_failure_blocks_downstream_and_keeps_failure_traces(
    tmp_path: Path,
) -> None:
    payload = asyncio.run(
        run_planner_demo(
            output_dir=tmp_path,
            fail_task_id="draft-validation-checklist",
        )
    )

    assert payload["status"] == "error"
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["failed_task_ids"] == ["draft-validation-checklist"]
    assert payload["blocked_task_ids"] == ["publish-summary"]

    run_dir = Path(str(payload["run_dir"]))
    plan_path = Path(str(payload["plan_path"]))
    summary_path = Path(str(payload["summary_path"]))
    event_log_path = Path(str(payload["event_log_path"]))

    assert plan_path.exists()
    assert summary_path.exists()
    assert event_log_path.exists()

    summary_payload = _read_json(summary_path)
    events = _read_events(event_log_path)
    task_artifact_names = sorted(path.name for path in (run_dir / "artifacts" / "tasks").iterdir())

    assert summary_payload["failed_count"] == 1
    assert summary_payload["blocked_count"] == 1
    assert task_artifact_names == [
        "capture-objective.json",
        "draft-work-breakdown.json",
    ]

    event_types = [event["type"] for event in events]
    assert "system.error" in event_types
    assert "task.failed" in event_types
    assert "task.blocked" in event_types
    assert event_types[-1] == "system.complete"


def test_task_graph_runner_preserves_explicit_run_dir_and_actual_artifact_paths(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "custom-run-root"
    planner_store_root = tmp_path / "planner-layout" / "planner-artifacts"
    task_store_root = tmp_path / "task-layout" / "task-artifacts"
    actual_artifact_root = tmp_path / "external-artifacts"
    event_log_path = tmp_path / "logs" / "events.jsonl"

    class StubExecutor:
        async def execute(self, task, dependency_handoffs):
            artifact_path = actual_artifact_root / f"{task.id}-result.json"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(
                json.dumps({"task_id": task.id, "handoff_count": len(dependency_handoffs)}),
                encoding="utf-8",
            )
            return TaskExecutionOutput(
                artifact_path=artifact_path,
                assistant_text=f"{task.description} complete.",
            )

    graph = TaskGraph(
        scenario_name="custom-run-layout",
        tasks=(
            PlannedTask(
                id="capture-objective",
                description="Capture the objective.",
                assignee="ba",
                order_index=1,
            ),
            PlannedTask(
                id="publish-summary",
                description="Publish the summary.",
                assignee="writer",
                order_index=2,
                dependencies=("capture-objective",),
            ),
        ),
    )
    validate_task_graph(graph)

    runner = TaskGraphRunner(
        run_dir=run_dir,
        planner_artifact_store=ArtifactStore(planner_store_root),
        task_artifact_store=ArtifactStore(task_store_root),
        event_bus=EventBus(JsonlEventStore(event_log_path)),
        task_executor=StubExecutor(),
    )

    result = asyncio.run(runner.run(graph, run_id="custom-run-id"))

    assert result.run_dir == run_dir
    assert result.plan_path == planner_store_root / "plan.json"
    assert result.summary_path == planner_store_root / "execution-summary.json"
    assert result.event_log_path == event_log_path
    assert result.artifact_paths == (
        actual_artifact_root / "capture-objective-result.json",
        actual_artifact_root / "publish-summary-result.json",
    )
