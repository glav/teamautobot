# D2 Plan: LLM Interface Decision

**Status**: Completed — ADR accepted in `docs/decision-records/2026-03-12-llm-interface-strategy.md`

## Goal

Decide how TeamAutobot should call LLMs without undermining the accepted D1 decision to keep the runtime repo-owned. The main options are:

- GitHub Copilot SDK
- direct provider SDKs
- a gateway/abstraction layer such as LiteLLM

## Decision boundaries

This plan is about the **LLM interface strategy** only.

It does **not** decide:

- the agent runtime ownership model (already decided in D1)
- event transport (D3)
- agent persistence topology (D5)
- the final default model/provider mix

## Current repository baseline

- The repository does **not** currently implement TeamAutobot with any LLM SDK in source code.
- If `github-copilot-sdk==0.1.32` is present in broader repo tooling, it is there to support parallel TeamBot review workflows.
- Copilot SDK should therefore be treated as a **candidate for D2**, not as the default implementation baseline for TeamAutobot.

## Decision drivers

The D2 decision should optimize for:

1. tool-calling fidelity and access to current provider capabilities
2. fit with the D1 custom runtime decision
3. debugging quality and error transparency
4. multi-provider flexibility and future switching cost
5. operational simplicity
6. observability and control over retries/fallbacks

## Source snapshot

### GitHub Copilot SDK

Primary source reviewed:

- `github/copilot-sdk` `python/README.md`

Key observations:

- Python SDK is in **technical preview**
- it exposes sessions, events, tools, hooks, streaming, and custom providers
- it talks to Copilot CLI over JSON-RPC and can auto-start the CLI
- it is more than a thin LLM client; it already includes execution/session behavior

### Direct provider SDKs

Primary sources reviewed:

- `openai/openai-python` `README.md`
- `anthropics/anthropic-sdk-python` `README.md`
- Anthropic tool-use docs: `https://docs.anthropic.com/en/docs/build-with-claude/tool-use`

Key observations:

- OpenAI SDK provides typed sync/async clients and streaming support
- Anthropic SDK provides first-party Python access and tool-use support
- Anthropic docs explicitly support tool use and strict schema conformance
- direct SDKs expose the most provider-native capabilities, but require more adapter work

### Gateway / abstraction

Primary source reviewed:

- `BerriAI/litellm` `README.md`

Key observations:

- LiteLLM can be used as either a Python SDK or a proxy/gateway
- it exposes a unified OpenAI-style interface across many providers
- it supports routing, retries/fallbacks, and centralized gateway concerns
- it can simplify multi-provider access, but adds an abstraction layer and possibly another service to run

## First-pass comparison matrix

| Option | Tool-calling fidelity | Debug transparency | Provider portability | Operational simplicity | Coupling risk | Fit with D1 |
|--------|-----------------------|--------------------|----------------------|------------------------|---------------|-------------|
| GitHub Copilot SDK | Medium-high | Medium | Medium-high | Medium-high for GitHub-centric workflows | High | Medium-low |
| Direct provider SDKs | High | High | Medium | Medium-low | Low | High |
| LiteLLM / gateway | Medium | Medium | High | Medium | Medium | Medium-high |

Notes:

- Copilot SDK is strong for batteries-included agentic workflows, but that is also why it has higher coupling risk relative to D1.
- Direct SDKs best preserve control and latest provider features, but they push integration work into TeamAutobot.
- LiteLLM is attractive when multi-provider routing, fallback, and central policy matter, but it should stay behind a TeamAutobot-owned interface if chosen.
- Retry/backoff policy, timeout budgets, cancellation, and orchestration behavior should remain runtime-owned; adapters should normalize provider-native failures into a TeamAutobot error shape.
- Phase 1 should validate one concrete provider adapter first and avoid over-generalizing before a second provider is actually needed.

## Decision outcome

Accepted direction for D2:

**TeamAutobot should define its own internal LLM client interface and initially implement it with direct provider SDK adapters.**

This keeps the runtime aligned with D1, preserves access to first-party tool-calling features, and avoids making TeamAutobot dependent on either Copilot CLI semantics or a gateway product as its core interface.

Under this direction:

- **Copilot SDK** remains a valid integration path for internal tooling or review workflows, but not the default product dependency
- **LiteLLM** remains a valid later option behind the same internal interface if multi-provider routing, spend controls, or gateway policies become important

## Next steps

1. Define the minimum internal LLM client interface TeamAutobot actually needs as a code-level protocol or implementation design note
2. Choose the first concrete provider adapter to validate the accepted interface
3. Decide whether streaming should remain optional in Phase 1 after the first adapter is validated
4. Revisit whether a gateway is needed only after direct-adapter needs are understood
