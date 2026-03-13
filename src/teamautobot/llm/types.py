from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class LLMErrorKind(StrEnum):
    AUTHENTICATION = "authentication"
    INVALID_REQUEST = "invalid_request"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    PROTOCOL = "protocol"


@dataclass(frozen=True, slots=True)
class ModelSelection:
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class LLMToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LLMRequest:
    instructions: str
    input: str
    tools: tuple[LLMToolDefinition, ...] = ()
    selection: ModelSelection | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    tool_calls: tuple[LLMToolCall, ...] = ()
    finish_reason: str = "stop"
    usage: Mapping[str, int] = field(default_factory=dict)
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class LLMError:
    kind: LLMErrorKind
    message: str
    provider: str | None = None
    retryable: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LLMResult:
    response: LLMResponse | None = None
    error: LLMError | None = None

    def __post_init__(self) -> None:
        if (self.response is None) == (self.error is None):
            raise ValueError("LLMResult must contain exactly one of response or error")

    @property
    def is_error(self) -> bool:
        return self.error is not None


class LLMClient(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResult:
        """Submit a single TeamAutobot-owned model turn."""
