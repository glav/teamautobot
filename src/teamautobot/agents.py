from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .artifacts import Artifact, ArtifactStore
from .events import EventBus
from .llm import LLMClient, LLMError, LLMRequest, LLMResult, ModelSelection
from .tools import ToolExecutionResult, ToolRegistry


@dataclass(frozen=True, slots=True)
class AgentTask:
    id: str
    description: str


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    task: AgentTask
    assistant_text: str
    tool_results: tuple[ToolExecutionResult, ...]
    artifact: Artifact
    model_selection: ModelSelection | None
    event_count: int


class AgentRunError(RuntimeError):
    def __init__(self, error: LLMError) -> None:
        super().__init__(error.message)
        self.error = error


class SingleTaskAgent:
    def __init__(
        self,
        *,
        agent_id: str,
        instructions: str,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        event_bus: EventBus,
        artifact_store: ArtifactStore,
    ) -> None:
        self._agent_id = agent_id
        self._instructions = instructions
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._event_bus = event_bus
        self._artifact_store = artifact_store

    async def run_task(
        self,
        task: AgentTask,
        *,
        selection: ModelSelection | None = None,
    ) -> AgentRunResult:
        self._event_bus.emit(
            "task.started",
            source=self._agent_id,
            correlation_id=task.id,
            payload={"task_id": task.id, "description": task.description},
        )

        initial_payload = json.dumps(
            {"task": {"id": task.id, "description": task.description}},
            sort_keys=True,
        )
        initial_response = await self._complete_once(initial_payload, selection)

        tool_results: list[ToolExecutionResult] = []
        for tool_call in initial_response.tool_calls:
            self._event_bus.emit(
                "tool.called",
                source=self._agent_id,
                correlation_id=task.id,
                payload={
                    "task_id": task.id,
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            )
            tool_result = self._tool_registry.call(tool_call.name, tool_call.arguments)
            tool_results.append(tool_result)
            self._event_bus.emit(
                "tool.completed",
                source=self._agent_id,
                correlation_id=task.id,
                payload={
                    "task_id": task.id,
                    "tool_name": tool_result.tool_name,
                    "output": tool_result.output,
                },
            )

        final_text = initial_response.text
        if tool_results:
            followup_payload = json.dumps(
                {
                    "task": {"id": task.id, "description": task.description},
                    "tool_results": [
                        {
                            "tool_name": result.tool_name,
                            "arguments": result.arguments,
                            "output": result.output,
                        }
                        for result in tool_results
                    ],
                },
                sort_keys=True,
            )
            final_response = await self._complete_once(followup_payload, selection)
            final_text = final_response.text

        artifact_payload: dict[str, Any] = {
            "task": {"id": task.id, "description": task.description},
            "agent_id": self._agent_id,
            "assistant_text": final_text,
            "tool_results": [
                {
                    "tool_name": result.tool_name,
                    "arguments": result.arguments,
                    "output": result.output,
                }
                for result in tool_results
            ],
            "model_selection": {
                "provider": selection.provider if selection else None,
                "model": selection.model if selection else None,
            },
        }
        artifact = self._artifact_store.write_json(task.id, artifact_payload)
        self._event_bus.emit(
            "artifact.created",
            source=self._agent_id,
            correlation_id=task.id,
            payload={"task_id": task.id, "artifact_path": str(artifact.path)},
        )
        self._event_bus.emit(
            "task.completed",
            source=self._agent_id,
            correlation_id=task.id,
            payload={"task_id": task.id, "artifact_path": str(artifact.path)},
        )

        return AgentRunResult(
            task=task,
            assistant_text=final_text,
            tool_results=tuple(tool_results),
            artifact=artifact,
            model_selection=selection,
            event_count=len(self._event_bus.events),
        )

    async def _complete_once(self, payload: str, selection: ModelSelection | None) -> Any:
        request = LLMRequest(
            instructions=self._instructions,
            input=payload,
            tools=self._tool_registry.definitions(),
            selection=selection,
        )
        result: LLMResult = await self._llm_client.complete(request)
        if result.error is not None:
            self._event_bus.emit(
                "system.error",
                source=self._agent_id,
                payload={"kind": result.error.kind, "message": result.error.message},
            )
            raise AgentRunError(result.error)
        assert result.response is not None
        return result.response
