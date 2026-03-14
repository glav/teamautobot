from __future__ import annotations

from .interfaces import Planner
from .models import PlannedTask, TaskGraph
from .validation import validate_task_graph

DEMO_SCENARIO_NAME = "planner-demo"


class StaticPlanner(Planner):
    def __init__(self, *, scenario_name: str = DEMO_SCENARIO_NAME) -> None:
        self._scenario_name = scenario_name

    def build_plan(self) -> TaskGraph:
        graph = TaskGraph(
            scenario_name=self._scenario_name,
            tasks=(
                PlannedTask(
                    id="capture-objective",
                    description="Capture the approved objective and restate the execution goal.",
                    assignee="ba",
                    order_index=1,
                ),
                PlannedTask(
                    id="draft-work-breakdown",
                    description="Draft a concise work breakdown for the approved objective.",
                    assignee="pm",
                    order_index=2,
                    dependencies=("capture-objective",),
                ),
                PlannedTask(
                    id="draft-validation-checklist",
                    description="Draft a concise validation checklist for the approved objective.",
                    assignee="reviewer",
                    order_index=3,
                    dependencies=("capture-objective",),
                ),
                PlannedTask(
                    id="publish-summary",
                    description=(
                        "Publish a final summary that combines the work breakdown "
                        "and validation checklist."
                    ),
                    assignee="writer",
                    order_index=4,
                    dependencies=("draft-work-breakdown", "draft-validation-checklist"),
                ),
            ),
        )
        validate_task_graph(graph)
        return graph
