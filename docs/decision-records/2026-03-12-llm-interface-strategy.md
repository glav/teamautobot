# Decision Record: Define Internal LLM Client Interface

- **Status**: Accepted
- **Deciders**: Repository owner, implementation agent
- **Date**: 12 March 2026
- **Related Docs**:
  - [`docs/teamautobot-design.md` — D2 LLM Interface](../teamautobot-design.md#42-llm-interface)
  - [`docs/teamautobot-design.md` — Open Decision Log](../teamautobot-design.md#8-open-decision-log)
  - [`docs/plans/2026-03-12-d2-llm-interface-decision-plan.md`](../plans/2026-03-12-d2-llm-interface-decision-plan.md)
  - [`docs/decision-records/2026-03-12-custom-agent-runtime.md`](./2026-03-12-custom-agent-runtime.md)
  - [`AGENTS.md`](../../AGENTS.md)

## Context

D1 is now accepted: TeamAutobot will use a custom, repo-owned runtime. That means D2 should choose an LLM access strategy that preserves runtime ownership instead of quietly reintroducing framework ownership through the model layer.

The repository does not currently implement TeamAutobot with any LLM SDK in source code. If `github-copilot-sdk==0.1.32` exists in the broader repo/tooling context, it is there to support parallel TeamBot review workflows and should not be treated as the implementation baseline for TeamAutobot unless D2 explicitly chooses it.

The main D2 options are:

- use GitHub Copilot SDK as the primary interface
- use direct provider SDKs as the primary interface
- use a gateway/abstraction layer such as LiteLLM as the primary interface

Current source review indicates:

- **GitHub Copilot SDK** is in technical preview and already provides sessions, events, tools, hooks, streaming, and custom providers through a JSON-RPC interface to Copilot CLI
- **Direct provider SDKs** expose the most provider-native capabilities and fastest access to tool-calling features
- **LiteLLM** can act as either a Python SDK or a proxy/gateway with unified multi-provider access, routing, and policy features

## Decision

Decision: TeamAutobot will define its **own internal LLM client interface** and initially implement that interface with **direct provider SDK adapters**.

Under this decision:

- the TeamAutobot runtime owns the client abstraction, request/response shapes, and retry/error semantics it depends on
- the TeamAutobot runtime owns retry policy, backoff policy, timeout budgets, cancellation behavior, and decisions to retry, fail, or escalate
- direct provider SDKs sit behind TeamAutobot-owned adapters
- GitHub Copilot SDK remains an optional integration path for internal tooling/review workflows, not the default product dependency
- LiteLLM or another gateway can still be added later behind the same TeamAutobot-owned interface if routing, fallback, or policy needs justify it

## Decision boundaries / non-goals

This ADR decides **LLM interface ownership and initial integration direction**.

It does **not** decide:

- the default production model or provider mix
- whether TeamAutobot will eventually use one provider or several
- whether a gateway such as LiteLLM will be required later
- prompt design, agent memory policy, or orchestration semantics outside the client boundary

Litmus test: if changing LLM providers or swapping in a gateway requires redesigning TeamAutobot's core runtime concepts instead of replacing an adapter, then D2 has failed to keep interface ownership inside the repository.

### Retry, timeout, and error ownership

- Adapters own provider-specific request translation and provider-specific response parsing.
- Adapters normalize provider-native failures into a stable TeamAutobot error shape while preserving provider diagnostic details.
- The runtime owns policy retries, backoff, timeout budgets, cancellation, and orchestration behavior after a failure.
- Adapters should not implement hidden policy retries. Any unavoidable SDK-level retry behavior must be minimized, configured explicitly, and documented.

This boundary is intentional: adapters translate and normalize, while the runtime decides what to do next.

### Phase 1 minimum interface contract

Phase 1 should keep the internal client contract intentionally small.

**Required operations**

- submit a single model turn asynchronously using TeamAutobot-owned input structures
- provide model instructions/input plus zero or more tool definitions
- return assistant text output plus zero or more tool calls
- return finish/usage metadata needed by the runtime

**Required first-class capabilities**

- tool calling
- text responses
- per-call model/provider selection
- normalized error results

**Optional capabilities for Phase 1**

- streaming
- strict structured outputs beyond tool schemas
- multimodal input/output
- provider-native server-side tools
- multi-provider routing and fallback

**Normalized error surface**

The minimum normalized error surface should distinguish at least:

- authentication/configuration failure
- invalid request or schema failure
- rate-limit or quota failure
- timeout or cancellation
- transient provider/service failure
- unsupported capability
- provider protocol/response failure

**Phase 1 guardrail**

Phase 1 should validate **one concrete provider adapter first**. Multi-provider support can be added later, but the interface should not be generalized beyond the first proven adapter unless a second provider requirement is explicit.

## Consequences

This keeps the LLM layer aligned with D1. TeamAutobot preserves direct access to provider-native capabilities such as tool calling, structured outputs, streaming, and evolving APIs, while keeping its own runtime abstractions independent of any one external SDK or gateway.

The trade-off is more implementation work. TeamAutobot must define and maintain provider adapters, normalize capability differences, and own more of the error-handling and compatibility surface itself. This is a deliberate trade in favor of control and long-term flexibility.

This decision still leaves room for operational pragmatism. If gateway concerns such as routing, spend controls, or centralized policy become important, LiteLLM or a similar product can still be introduced behind the internal client interface instead of becoming the interface itself.

## Alternatives Considered

### Comparison matrix

| Option | Tool-calling fidelity | Debug transparency | Provider portability | Operational simplicity | Coupling risk | Fit with D1 |
|--------|-----------------------|--------------------|----------------------|------------------------|---------------|-------------|
| GitHub Copilot SDK | Medium-high | Medium | Medium-high | Medium-high for GitHub-centric workflows | High | Medium-low |
| Direct provider SDKs behind internal interface | High | High | Medium | Medium-low | Low | High |
| LiteLLM / gateway as primary interface | Medium | Medium | High | Medium | Medium | Medium-high |

This matrix is qualitative. It is meant to compare architectural fit for D2, not total framework quality.

### Use GitHub Copilot SDK as the primary LLM interface

GitHub Copilot SDK is attractive because it already supports sessions, tools, hooks, streaming, custom providers, and GitHub-based authentication patterns. It could accelerate implementation in environments where Copilot-native workflows are already central.

It is not the accepted direction because it is more than a thin LLM SDK: it already carries session and execution behavior through the Copilot CLI model. That makes it better suited as an integration path or internal-tooling option than as the primary product dependency for TeamAutobot's core runtime.

If used later behind the TeamAutobot-owned interface, it must not take ownership of TeamAutobot session semantics, event semantics, or tool-orchestration behavior.

### Use a gateway/abstraction layer as the primary interface

LiteLLM and similar products are attractive because they simplify multi-provider access, standardize interfaces, and can add routing, fallback, and centralized policy controls.

They are not the accepted direction because they insert another abstraction layer between TeamAutobot and provider-native capabilities. For Phase 1, that is likely premature unless gateway features are already known to be required. They remain good candidates behind the TeamAutobot-owned interface later.

If used later behind the TeamAutobot-owned interface, they must not take ownership of TeamAutobot session semantics, event semantics, or tool-orchestration behavior.

### Use direct provider SDKs behind an internal TeamAutobot interface

This is the accepted direction because it best preserves control, debuggability, and access to current provider-native features while still allowing the repository to define a stable internal contract.

The main cost is adapter work and capability normalization, but that work aligns with the accepted choice to keep the runtime repo-owned.

## Follow-up Actions

- Define the first concrete provider adapter to validate the Phase 1 interface
- Turn the Phase 1 minimum interface contract into a small implementation design note or code-level protocol
- Identify which features must be normalized at the interface layer: tool calls, structured outputs, finish/usage metadata, and error types
- Keep Copilot SDK and LiteLLM as optional adapters/integrations until proven necessary as primary dependencies

## Notes

Primary sources reviewed for this decision:

- `github/copilot-sdk` `python/README.md`
- `openai/openai-python` `README.md`
- `anthropics/anthropic-sdk-python` `README.md`
- Anthropic tool-use docs: `https://docs.anthropic.com/en/docs/build-with-claude/tool-use`
- `BerriAI/litellm` `README.md`
