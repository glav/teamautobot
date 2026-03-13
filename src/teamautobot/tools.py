from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .llm import LLMToolDefinition


class ToolNotFoundError(KeyError):
    """Raised when a tool call references an unregistered tool."""


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    tool_name: str
    arguments: dict[str, Any]
    output: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Tool:
    definition: LLMToolDefinition
    handler: Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.definition.name] = tool

    def definitions(self) -> tuple[LLMToolDefinition, ...]:
        return tuple(tool.definition for tool in self._tools.values())

    def call(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        output = tool.handler(arguments)
        return ToolExecutionResult(tool_name=name, arguments=arguments, output=output)
