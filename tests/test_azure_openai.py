from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from teamautobot.llm import (
    AzureOpenAIAuthMode,
    LLMErrorKind,
    LLMRequest,
    LLMToolDefinition,
    ModelSelection,
)
from teamautobot.llm.azure_openai import (
    AzureOpenAIConfig,
    AzureOpenAIResponsesClient,
    map_azure_openai_error,
    normalize_azure_openai_endpoint,
    parse_azure_openai_auth_mode,
    resolve_azure_openai_config,
)


@dataclass
class StubUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass
class StubOutput:
    type: str
    name: str | None = None
    arguments: str | None = None
    call_id: str | None = None


@dataclass
class StubResponse:
    output_text: str
    output: tuple[StubOutput, ...]
    usage: StubUsage | None = None
    model: str | None = None
    status: str = "completed"
    incomplete_details: object | None = None
    error: object | None = None


@dataclass
class StubIncompleteDetails:
    reason: str


@dataclass
class StubResponseError:
    message: str
    code: str | None = None
    type: str | None = None
    param: str | None = None


class StubResponsesAPI:
    def __init__(self, response: StubResponse | Exception) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> StubResponse:
        self.calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class StubOpenAIClient:
    def __init__(self, response: StubResponse | Exception) -> None:
        self.responses = StubResponsesAPI(response)


def test_normalize_azure_openai_endpoint_appends_v1_path() -> None:
    assert (
        normalize_azure_openai_endpoint("https://example.openai.azure.com")
        == "https://example.openai.azure.com/openai/v1/"
    )
    assert (
        normalize_azure_openai_endpoint("https://example.openai.azure.com/openai/v1/")
        == "https://example.openai.azure.com/openai/v1/"
    )


def test_resolve_azure_openai_config_reads_environment() -> None:
    config = resolve_azure_openai_config(
        {
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
            "AZURE_OPENAI_API_KEY": "secret",
            "AZURE_OPENAI_MODEL_DEPLOYMENT": "gpt-4.1-nano",
        }
    )

    assert config.base_url == "https://example.openai.azure.com/openai/v1/"
    assert config.is_configured is True
    assert config.resolved_auth_mode is AzureOpenAIAuthMode.API_KEY
    assert config.missing_fields() == ()


def test_resolve_azure_openai_config_supports_rbac_without_api_key() -> None:
    config = resolve_azure_openai_config(
        {
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
            "AZURE_OPENAI_MODEL_DEPLOYMENT": "gpt-4.1-nano",
            "AZURE_OPENAI_AUTH_MODE": "rbac",
        }
    )

    assert config.is_configured is True
    assert config.auth_mode is AzureOpenAIAuthMode.RBAC
    assert config.resolved_auth_mode is AzureOpenAIAuthMode.RBAC
    assert config.missing_fields() == ()


def test_parse_azure_openai_auth_mode_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="AZURE_OPENAI_AUTH_MODE"):
        parse_azure_openai_auth_mode("magic")


def test_azure_openai_client_maps_responses_api_payload() -> None:
    response = StubResponse(
        output_text="Tool call requested.",
        output=(
            StubOutput(
                type="function_call",
                name="get_weather",
                arguments='{"location": "Sydney"}',
                call_id="call_123",
            ),
        ),
        usage=StubUsage(input_tokens=11, output_tokens=7, total_tokens=18),
        model="gpt-4.1-nano",
    )
    openai_client = StubOpenAIClient(response)
    client = AzureOpenAIResponsesClient(
        config_resolver=lambda: AzureOpenAIConfig(
            endpoint="https://example.openai.azure.com",
            api_key="secret",
            model_deployment="gpt-4.1-nano",
        ),
        client_factory=lambda config: openai_client,
    )
    request = LLMRequest(
        instructions="Be helpful",
        input="What's the weather?",
        tools=(
            LLMToolDefinition(
                name="get_weather",
                description="Look up weather",
                input_schema={"type": "object", "properties": {"location": {"type": "string"}}},
            ),
        ),
        selection=ModelSelection(provider="azure_openai", model="gpt-4.1-nano"),
    )

    result = asyncio.run(client.complete(request))

    assert result.error is None
    assert result.response is not None
    assert result.response.text == "Tool call requested."
    assert result.response.finish_reason == "tool_calls"
    assert result.response.provider == "azure_openai"
    assert result.response.model == "gpt-4.1-nano"
    assert result.response.usage == {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
    assert result.response.tool_calls[0].name == "get_weather"
    assert result.response.tool_calls[0].arguments == {"location": "Sydney"}
    assert openai_client.responses.calls == [
        {
            "model": "gpt-4.1-nano",
            "instructions": "Be helpful",
            "input": "What's the weather?",
            "tools": [
                {
                    "type": "function",
                    "name": "get_weather",
                    "description": "Look up weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                    },
                }
            ],
        }
    ]


def test_azure_openai_client_returns_protocol_error_for_invalid_tool_arguments() -> None:
    client = AzureOpenAIResponsesClient(
        config_resolver=lambda: AzureOpenAIConfig(
            endpoint="https://example.openai.azure.com",
            api_key="secret",
            model_deployment="gpt-4.1-nano",
        ),
        client_factory=lambda config: StubOpenAIClient(
            StubResponse(
                output_text="",
                output=(
                    StubOutput(
                        type="function_call",
                        name="get_weather",
                        arguments='["not-an-object"]',
                        call_id="call_123",
                    ),
                ),
            )
        ),
    )

    result = asyncio.run(client.complete(LLMRequest(instructions="Be helpful", input="hi")))

    assert result.response is None
    assert result.error is not None
    assert result.error.kind == LLMErrorKind.PROTOCOL
    assert result.error.provider == "azure_openai"


@pytest.mark.parametrize("reason", ["max_output_tokens", "content_filter"])
def test_azure_openai_client_returns_error_for_incomplete_response(reason: str) -> None:
    client = AzureOpenAIResponsesClient(
        config_resolver=lambda: AzureOpenAIConfig(
            endpoint="https://example.openai.azure.com",
            api_key="secret",
            model_deployment="gpt-4.1-nano",
        ),
        client_factory=lambda config: StubOpenAIClient(
            StubResponse(
                output_text="Partial",
                output=(),
                model="gpt-4.1-nano",
                status="incomplete",
                incomplete_details=StubIncompleteDetails(reason=reason),
            )
        ),
    )

    result = asyncio.run(client.complete(LLMRequest(instructions="Be helpful", input="hi")))

    assert result.response is None
    assert result.error is not None
    assert result.error.kind == LLMErrorKind.PROTOCOL
    assert result.error.provider == "azure_openai"
    assert result.error.raw["status"] == "incomplete"
    assert result.error.raw["incomplete_details"] == {"reason": reason}
    assert reason in result.error.message


def test_azure_openai_client_returns_error_for_failed_response() -> None:
    client = AzureOpenAIResponsesClient(
        config_resolver=lambda: AzureOpenAIConfig(
            endpoint="https://example.openai.azure.com",
            api_key="secret",
            model_deployment="gpt-4.1-nano",
        ),
        client_factory=lambda config: StubOpenAIClient(
            StubResponse(
                output_text="",
                output=(),
                model="gpt-4.1-nano",
                status="failed",
                error=StubResponseError(
                    message="The provider failed to complete the response.",
                    code="server_error",
                    type="server_error",
                ),
            )
        ),
    )

    result = asyncio.run(client.complete(LLMRequest(instructions="Be helpful", input="hi")))

    assert result.response is None
    assert result.error is not None
    assert result.error.kind == LLMErrorKind.TRANSIENT
    assert result.error.provider == "azure_openai"
    assert result.error.retryable is True
    assert result.error.raw["status"] == "failed"
    assert result.error.raw["error"]["code"] == "server_error"
    assert "provider failed to complete the response" in result.error.message


def test_azure_openai_client_fails_clearly_when_model_missing() -> None:
    client = AzureOpenAIResponsesClient(
        config_resolver=lambda: AzureOpenAIConfig(
            endpoint="https://example.openai.azure.com",
            api_key="secret",
            model_deployment=None,
        ),
        client_factory=lambda config: StubOpenAIClient(AssertionError("should not be called")),
    )

    result = asyncio.run(client.complete(LLMRequest(instructions="Be helpful", input="hi")))

    assert result.response is None
    assert result.error is not None
    assert result.error.kind == LLMErrorKind.INVALID_REQUEST
    assert "AZURE_OPENAI_MODEL_DEPLOYMENT" in result.error.message


def test_azure_openai_client_allows_rbac_without_api_key() -> None:
    openai_client = StubOpenAIClient(
        StubResponse(output_text="Hello", output=(), model="gpt-4.1-nano")
    )
    captured_configs: list[AzureOpenAIConfig] = []
    client = AzureOpenAIResponsesClient(
        config_resolver=lambda: AzureOpenAIConfig(
            endpoint="https://example.openai.azure.com",
            api_key=None,
            model_deployment="gpt-4.1-nano",
            auth_mode=AzureOpenAIAuthMode.RBAC,
        ),
        client_factory=lambda config: (
            captured_configs.append(config),
            openai_client,
        )[1],
    )

    result = asyncio.run(client.complete(LLMRequest(instructions="Be helpful", input="hi")))

    assert result.error is None
    assert captured_configs[0].resolved_auth_mode is AzureOpenAIAuthMode.RBAC


class AuthenticationError(Exception):
    status_code = 401


class RateLimitError(Exception):
    status_code = 429


class APITimeoutError(Exception):
    status_code = 408


class InternalServerError(Exception):
    status_code = 503


@pytest.mark.parametrize(
    ("exc", "kind", "retryable"),
    [
        (AuthenticationError("bad key"), LLMErrorKind.AUTHENTICATION, False),
        (RateLimitError("slow down"), LLMErrorKind.RATE_LIMIT, True),
        (APITimeoutError("timed out"), LLMErrorKind.TIMEOUT, True),
        (InternalServerError("try later"), LLMErrorKind.TRANSIENT, True),
    ],
)
def test_map_azure_openai_error(exc: Exception, kind: LLMErrorKind, retryable: bool) -> None:
    error = map_azure_openai_error(exc)

    assert error.kind == kind
    assert error.retryable is retryable
    assert error.provider == "azure_openai"
