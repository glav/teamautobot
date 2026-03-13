"""Internal LLM client contract and test doubles for TeamAutobot."""

from .fake import ScriptedLLMClient
from .types import (
    LLMClient,
    LLMError,
    LLMErrorKind,
    LLMRequest,
    LLMResponse,
    LLMResult,
    LLMToolCall,
    LLMToolDefinition,
    ModelSelection,
)

__all__ = [
    "LLMClient",
    "LLMError",
    "LLMErrorKind",
    "LLMRequest",
    "LLMResponse",
    "LLMResult",
    "LLMToolCall",
    "LLMToolDefinition",
    "ModelSelection",
    "ScriptedLLMClient",
]
