from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .types import (
    LLMClient,
    LLMError,
    LLMErrorKind,
    LLMRequest,
    LLMResponse,
    LLMResult,
    LLMToolCall,
)

_PROVIDER_NAME = "azure_openai"
_AZURE_OPENAI_SCOPE = "https://cognitiveservices.azure.com/.default"


class AzureOpenAIAuthMode(StrEnum):
    AUTO = "auto"
    API_KEY = "api_key"
    RBAC = "rbac"


@dataclass(frozen=True, slots=True)
class AzureOpenAIConfig:
    endpoint: str | None
    api_key: str | None
    model_deployment: str | None
    auth_mode: AzureOpenAIAuthMode = AzureOpenAIAuthMode.AUTO

    @property
    def base_url(self) -> str | None:
        if self.endpoint is None:
            return None
        return normalize_azure_openai_endpoint(self.endpoint)

    @property
    def resolved_auth_mode(self) -> AzureOpenAIAuthMode:
        if self.auth_mode is AzureOpenAIAuthMode.AUTO:
            return AzureOpenAIAuthMode.API_KEY if self.api_key else AzureOpenAIAuthMode.RBAC
        return self.auth_mode

    @property
    def is_configured(self) -> bool:
        return not self.missing_fields()

    def missing_fields(self, *, require_model: bool = True) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if self.resolved_auth_mode is AzureOpenAIAuthMode.API_KEY and not self.api_key:
            missing.append("AZURE_OPENAI_API_KEY")
        if require_model and not self.model_deployment:
            missing.append("AZURE_OPENAI_MODEL_DEPLOYMENT")
        return tuple(missing)


def normalize_azure_openai_endpoint(endpoint: str) -> str:
    value = endpoint.strip().rstrip("/")
    if not value:
        raise ValueError("AZURE_OPENAI_ENDPOINT must not be empty")

    if value.endswith("/openai/v1"):
        return f"{value}/"
    return f"{value}/openai/v1/"


def resolve_azure_openai_config(
    environ: Mapping[str, str] | None = None,
) -> AzureOpenAIConfig:
    env = os.environ if environ is None else environ
    endpoint = env.get("AZURE_OPENAI_ENDPOINT") or None
    api_key = env.get("AZURE_OPENAI_API_KEY") or None
    model_deployment = env.get("AZURE_OPENAI_MODEL_DEPLOYMENT") or None
    auth_mode = parse_azure_openai_auth_mode(env.get("AZURE_OPENAI_AUTH_MODE"))
    return AzureOpenAIConfig(
        endpoint=endpoint,
        api_key=api_key,
        model_deployment=model_deployment,
        auth_mode=auth_mode,
    )


def parse_azure_openai_auth_mode(raw_value: str | None) -> AzureOpenAIAuthMode:
    normalized = (raw_value or AzureOpenAIAuthMode.AUTO.value).strip().lower()
    try:
        return AzureOpenAIAuthMode(normalized)
    except ValueError as exc:
        raise ValueError(
            "AZURE_OPENAI_AUTH_MODE must be one of: auto, api_key, rbac."
        ) from exc


ClientFactory = Callable[[AzureOpenAIConfig], Any]
ConfigResolver = Callable[[], AzureOpenAIConfig]


class AzureOpenAIResponsesClient(LLMClient):
    def __init__(
        self,
        *,
        config_resolver: ConfigResolver = resolve_azure_openai_config,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._config_resolver = config_resolver
        self._client_factory = client_factory or _default_client_factory

    async def complete(self, request: LLMRequest) -> LLMResult:
        try:
            config = self._config_resolver()
        except ValueError as exc:
            return LLMResult(
                error=LLMError(
                    kind=LLMErrorKind.INVALID_REQUEST,
                    message=str(exc),
                    provider=_PROVIDER_NAME,
                )
            )
        model = (
            request.selection.model
            if request.selection and request.selection.model
            else config.model_deployment
        )

        config_error = _validate_config(config=config, model=model)
        if config_error is not None:
            return LLMResult(error=config_error)

        try:
            client = self._client_factory(config)
            response = await asyncio.to_thread(
                client.responses.create,
                model=model,
                instructions=request.instructions,
                input=request.input,
                tools=_build_tools_payload(request),
            )
        except Exception as exc:  # pragma: no cover - exercised via mapping helper tests
            return LLMResult(error=map_azure_openai_error(exc))

        response_error = map_azure_openai_response_error(response)
        if response_error is not None:
            return LLMResult(error=response_error)

        try:
            mapped_response = map_azure_openai_response(response, requested_model=model)
        except Exception as exc:
            return LLMResult(
                error=LLMError(
                    kind=LLMErrorKind.PROTOCOL,
                    message=f"Azure OpenAI response could not be parsed: {exc}",
                    provider=_PROVIDER_NAME,
                    raw={"exception_type": type(exc).__name__},
                )
            )
        return LLMResult(response=mapped_response)


def _default_client_factory(config: AzureOpenAIConfig) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depends on environment setup
        raise RuntimeError(
            "The openai package is required for Azure OpenAI support. Run `uv sync`."
        ) from exc

    if config.resolved_auth_mode is AzureOpenAIAuthMode.API_KEY:
        return OpenAI(api_key=config.api_key, base_url=config.base_url, max_retries=0)

    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    except ImportError as exc:  # pragma: no cover - depends on environment setup
        raise RuntimeError(
            "The azure-identity package is required for Azure OpenAI RBAC support. "
            "Run `uv sync`."
        ) from exc

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        _AZURE_OPENAI_SCOPE,
    )
    return OpenAI(api_key=token_provider, base_url=config.base_url, max_retries=0)


def _validate_config(*, config: AzureOpenAIConfig, model: str | None) -> LLMError | None:
    if not config.endpoint:
        return LLMError(
            kind=LLMErrorKind.INVALID_REQUEST,
            message="Azure OpenAI endpoint is not configured. Set AZURE_OPENAI_ENDPOINT.",
            provider=_PROVIDER_NAME,
        )
    if (
        config.resolved_auth_mode is AzureOpenAIAuthMode.API_KEY
        and not config.api_key
    ):
        return LLMError(
            kind=LLMErrorKind.AUTHENTICATION,
            message="Azure OpenAI API key is not configured. Set AZURE_OPENAI_API_KEY.",
            provider=_PROVIDER_NAME,
        )
    if not model:
        return LLMError(
            kind=LLMErrorKind.INVALID_REQUEST,
            message=(
                "Azure OpenAI model deployment is not configured. "
                "Set AZURE_OPENAI_MODEL_DEPLOYMENT or pass --model."
            ),
            provider=_PROVIDER_NAME,
        )
    return None


def _build_tools_payload(request: LLMRequest) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        }
        for tool in request.tools
    ]


def map_azure_openai_response(response: Any, *, requested_model: str) -> LLMResponse:
    output_items = getattr(response, "output", None) or ()
    tool_calls = tuple(
        _map_tool_call(item)
        for item in output_items
        if getattr(item, "type", None) == "function_call"
    )
    return LLMResponse(
        text=getattr(response, "output_text", "") or "",
        tool_calls=tool_calls,
        finish_reason="tool_calls" if tool_calls else "stop",
        usage=_extract_usage(getattr(response, "usage", None)),
        provider=_PROVIDER_NAME,
        model=getattr(response, "model", None) or requested_model,
    )


def map_azure_openai_response_error(response: Any) -> LLMError | None:
    status = getattr(response, "status", None) or "completed"
    if status == "completed":
        return None

    raw: dict[str, Any] = {"status": status}

    if status == "incomplete":
        incomplete_details = _extract_payload(
            getattr(response, "incomplete_details", None),
            fields=("reason",),
        )
        if incomplete_details:
            raw["incomplete_details"] = incomplete_details

        reason = incomplete_details.get("reason")
        message = "Azure OpenAI response was incomplete."
        if reason:
            message = f"Azure OpenAI response was incomplete: {reason}."
        return LLMError(
            kind=LLMErrorKind.PROTOCOL,
            message=message,
            provider=_PROVIDER_NAME,
            raw=raw,
        )

    error_payload = _extract_payload(
        getattr(response, "error", None),
        fields=("message", "code", "type", "param"),
    )
    if error_payload:
        raw["error"] = error_payload

    if status == "cancelled":
        return LLMError(
            kind=LLMErrorKind.TIMEOUT,
            message=_response_state_message(
                status=status,
                error_payload=error_payload,
                fallback="Azure OpenAI response was cancelled.",
            ),
            provider=_PROVIDER_NAME,
            raw=raw,
        )

    if status == "failed":
        kind = _response_error_kind(error_payload)
        return LLMError(
            kind=kind,
            message=_response_state_message(
                status=status,
                error_payload=error_payload,
                fallback="Azure OpenAI response failed.",
            ),
            provider=_PROVIDER_NAME,
            retryable=kind
            in {
                LLMErrorKind.RATE_LIMIT,
                LLMErrorKind.TIMEOUT,
                LLMErrorKind.TRANSIENT,
            },
            raw=raw,
        )

    return LLMError(
        kind=LLMErrorKind.PROTOCOL,
        message=f"Azure OpenAI response returned unexpected status: {status}.",
        provider=_PROVIDER_NAME,
        raw=raw,
    )


def _map_tool_call(item: Any) -> LLMToolCall:
    name = getattr(item, "name", None)
    call_id = getattr(item, "call_id", None)
    raw_arguments = getattr(item, "arguments", "{}")
    if not name or not call_id:
        raise ValueError("Function call output is missing name or call_id")

    arguments = raw_arguments
    if isinstance(raw_arguments, str):
        arguments = json.loads(raw_arguments or "{}")
    if not isinstance(arguments, dict):
        raise ValueError("Function call arguments must decode to an object")

    return LLMToolCall(id=call_id, name=name, arguments=arguments)


def _extract_usage(usage: Any) -> dict[str, int]:
    if usage is None:
        return {}

    fields = ("input_tokens", "output_tokens", "total_tokens")
    payload: dict[str, int] = {}
    for field in fields:
        value = usage.get(field) if isinstance(usage, Mapping) else getattr(usage, field, None)
        if isinstance(value, int):
            payload[field] = value
    return payload


def _extract_payload(value: Any, *, fields: tuple[str, ...]) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items() if item is not None}

    payload: dict[str, Any] = {}
    for field in fields:
        item = getattr(value, field, None)
        if item is not None:
            payload[field] = item
    return payload


def _response_state_message(
    *,
    status: str,
    error_payload: Mapping[str, Any],
    fallback: str,
) -> str:
    message = error_payload.get("message")
    if isinstance(message, str) and message:
        return f"Azure OpenAI response {status}: {message}"
    return fallback


def _response_error_kind(error_payload: Mapping[str, Any]) -> LLMErrorKind:
    tokens = {
        str(error_payload[field]).lower()
        for field in ("code", "type")
        if error_payload.get(field) is not None
    }
    if tokens & {
        "authentication_error",
        "unauthorized",
        "forbidden",
        "permission_denied",
    }:
        return LLMErrorKind.AUTHENTICATION
    if tokens & {
        "rate_limit_error",
        "rate_limit_exceeded",
        "insufficient_quota",
        "quota_exceeded",
    }:
        return LLMErrorKind.RATE_LIMIT
    if tokens & {"timeout", "request_timeout"}:
        return LLMErrorKind.TIMEOUT
    if tokens & {"server_error", "internal_server_error", "api_connection_error"}:
        return LLMErrorKind.TRANSIENT
    if tokens & {
        "invalid_request_error",
        "bad_request",
        "content_filter",
        "not_found",
        "unprocessable_entity",
    }:
        return LLMErrorKind.INVALID_REQUEST
    return LLMErrorKind.PROTOCOL


def map_azure_openai_error(exc: Exception) -> LLMError:
    status_code = getattr(exc, "status_code", None)
    error_payload = {
        "exception_type": type(exc).__name__,
        "status_code": status_code,
    }

    if isinstance(exc, RuntimeError) and (
        "openai package is required" in str(exc)
        or "azure-identity package is required" in str(exc)
    ):
        return LLMError(
            kind=LLMErrorKind.UNSUPPORTED_CAPABILITY,
            message=str(exc),
            provider=_PROVIDER_NAME,
            raw=error_payload,
        )

    if status_code in {401, 403} or type(exc).__name__ in {
        "AuthenticationError",
        "PermissionDeniedError",
    }:
        return LLMError(
            kind=LLMErrorKind.AUTHENTICATION,
            message=str(exc),
            provider=_PROVIDER_NAME,
            raw=error_payload,
        )
    if status_code == 429 or type(exc).__name__ == "RateLimitError":
        return LLMError(
            kind=LLMErrorKind.RATE_LIMIT,
            message=str(exc),
            provider=_PROVIDER_NAME,
            retryable=True,
            raw=error_payload,
        )
    if status_code in {400, 404, 422} or type(exc).__name__ in {
        "BadRequestError",
        "NotFoundError",
        "UnprocessableEntityError",
    }:
        return LLMError(
            kind=LLMErrorKind.INVALID_REQUEST,
            message=str(exc),
            provider=_PROVIDER_NAME,
            raw=error_payload,
        )
    if status_code in {408, 504} or type(exc).__name__ in {"APITimeoutError", "TimeoutError"}:
        return LLMError(
            kind=LLMErrorKind.TIMEOUT,
            message=str(exc),
            provider=_PROVIDER_NAME,
            retryable=True,
            raw=error_payload,
        )
    if (status_code is not None and status_code >= 500) or type(exc).__name__ in {
        "APIConnectionError",
        "InternalServerError",
    }:
        return LLMError(
            kind=LLMErrorKind.TRANSIENT,
            message=str(exc),
            provider=_PROVIDER_NAME,
            retryable=True,
            raw=error_payload,
        )
    return LLMError(
        kind=LLMErrorKind.PROTOCOL,
        message=str(exc),
        provider=_PROVIDER_NAME,
        raw=error_payload,
    )
