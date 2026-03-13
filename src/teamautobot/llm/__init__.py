"""Internal LLM client contract and test doubles for TeamAutobot."""

from .azure_openai import (
    AzureOpenAIAuthMode,
    AzureOpenAIConfig,
    AzureOpenAIResponsesClient,
    normalize_azure_openai_endpoint,
    parse_azure_openai_auth_mode,
    resolve_azure_openai_config,
)
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
    "AzureOpenAIConfig",
    "AzureOpenAIResponsesClient",
    "AzureOpenAIAuthMode",
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
    "normalize_azure_openai_endpoint",
    "parse_azure_openai_auth_mode",
    "resolve_azure_openai_config",
]
