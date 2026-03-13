# Review: docs/decision-records/2026-03-12-llm-interface-strategy.md

**Decision**: NEEDS_REVISION

## Summary

The ADR is directionally strong and consistent with the v2 design doc, the accepted D1 runtime ADR, and the repository's ADR structure. It clearly protects repo ownership of the runtime and keeps Copilot SDK / gateway options as secondary integrations. The remaining problems are implementation-critical ambiguity around retry/error ownership and an interface definition that is still too abstract for safe Phase 1 execution.

## Issues

1. **[Major] Retry/error ownership is still ambiguous.**
   - ADR lines 37-40 say TeamBot v2 owns the client abstraction plus the retry/error semantics it depends on.
   - ADR lines 95-98 still list retries and error types as features to normalize at the interface layer.
   - The design doc also leaves this boundary open (`docs/teamautobot-design.md` lines 377-378 and 438-440).
   - This creates a real implementation risk: adapter-level retries, runtime-level retries, and provider error translation could end up split across layers, leading to duplicate retry behavior or inconsistent failure handling.

2. **[Major] The Phase 1 interface contract is not concrete enough to guide implementation safely.**
   - ADR lines 33-40 choose "internal interface + direct provider SDK adapters", but do not define the minimum contract that interface must expose.
   - ADR lines 95-98 defer core questions such as whether Phase 1 starts with one provider or several and which capabilities are first-class.
   - Without a tighter boundary, implementers can over-generalize too early or design incompatible adapter surfaces around messages, tool turns, structured outputs, streaming, and capability negotiation.

## Suggestions

- Add an explicit boundary statement for **retries, timeouts, provider errors, and normalization**. For example: adapters expose provider-native failures in a normalized shape, while policy retries and orchestration behavior remain runtime-owned.
- Add a short **Phase 1 minimum interface contract** to this ADR or a linked companion design note covering:
  - required operations,
  - required first-class capabilities,
  - normalized error surface,
  - whether streaming and tool use are mandatory contract features or optional capabilities,
  - what is intentionally out of scope for Phase 1.
- Clarify whether **Phase 1 should start with one concrete provider adapter** and expand later, or whether multi-provider support is an immediate requirement. If still undecided, add a guardrail against designing beyond the first validated adapter.
- Make the non-goal sharper for **Copilot SDK / gateway integrations**: they may sit behind the TeamBot-owned interface, but they must not take ownership of TeamBot session semantics, event semantics, or tool-orchestration behavior.
