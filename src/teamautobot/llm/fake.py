from __future__ import annotations

from collections.abc import Callable, Sequence

from .types import LLMClient, LLMError, LLMErrorKind, LLMRequest, LLMResponse, LLMResult

type ScriptStep = Callable[[LLMRequest], LLMResult | LLMResponse | LLMError]


class ScriptedLLMClient(LLMClient):
    """Deterministic scripted client for tests and local demo flows."""

    def __init__(self, steps: Sequence[ScriptStep]) -> None:
        self._steps = list(steps)
        self._index = 0

    async def complete(self, request: LLMRequest) -> LLMResult:
        if self._index >= len(self._steps):
            return LLMResult(
                error=LLMError(
                    kind=LLMErrorKind.PROTOCOL,
                    message="No scripted LLM step remained for the request",
                    provider=request.selection.provider if request.selection else None,
                )
            )

        step = self._steps[self._index]
        self._index += 1
        outcome = step(request)

        if isinstance(outcome, LLMResult):
            return outcome
        if isinstance(outcome, LLMResponse):
            return LLMResult(response=outcome)
        if isinstance(outcome, LLMError):
            return LLMResult(error=outcome)

        raise TypeError(f"Unsupported scripted outcome: {type(outcome)!r}")
