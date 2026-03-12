# Decision Record: Build Custom Agent Runtime

- **Status**: Accepted
- **Deciders**: Repository owner, implementation agent
- **Date**: 12 March 2026
- **Related Docs**:
  - [`docs/teamautobot-design.md` — D1 Agent Framework](../teamautobot-design.md#41-agent-framework)
  - [`docs/teamautobot-design.md` — Open Decision Log](../teamautobot-design.md#8-open-decision-log)
  - [`AGENTS.md`](../../AGENTS.md)

## Context

TeamBot v2, being developed in the TeamAutobot repository, is explicitly designed around autonomy, collaboration, adaptation, tools, memory, observability, and a minimal viable framework. The core runtime must support stateful agents, dynamic task graphs, event-driven coordination, replayability, configurable agent fan-out, and explicit control over agent lifecycle boundaries.

D1 asked whether the runtime should be built from scratch or whether TeamAutobot should adopt a lightweight agent library as the foundation. Heavy frameworks were already ruled out because they impose workflow and orchestration models that conflict with the design goal of emergent, constraint-bounded collaboration.

Lightweight libraries remain attractive because they can reduce boilerplate around tool calling, retries, and structured outputs. However, using one as the core runtime still risks coupling TeamAutobot to another project's assumptions about agent boundaries, orchestration style, memory, or handoff patterns.

Microsoft Agent Framework also needs to be considered explicitly. Based on Microsoft's documentation, it is not just a small helper library: it provides agents, graph-based workflows, state/session management, middleware, events, checkpointing, and multi-agent orchestration patterns. That makes it a credible option for TeamAutobot, but also places it much closer to "adopt a framework runtime" than to "use thin primitives."

AutoGen should also be considered explicitly. It is historically important in this space and introduced several influential multi-agent ideas, including GroupChat and an event-driven agent runtime. According to [Microsoft's migration guide from AutoGen to Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/migration-guide/from-autogen/), Agent Framework is the newer foundation they recommend for that ecosystem, so AutoGen is best treated here as both a live comparison point and important prior art rather than the default Microsoft-path choice.

## Decision

Decision: TeamAutobot will implement its **core agent runtime as a custom, repo-owned set of composable primitives**.

The custom runtime will own:

- agent task loop and lifecycle semantics
- agent pool semantics and dynamic spawn/release behavior
- tool registry and persona-based tool access
- working-memory and session-context boundaries
- event schemas and bus-facing runtime interfaces
- task graph execution and re-planning integration

External libraries are still allowed, but only as **supporting dependencies**, not as the owning runtime. Examples include:

- provider SDKs for LLM access
- validation/structured-output libraries
- retry, logging, and telemetry utilities
- isolated spikes or comparison prototypes

TeamAutobot will **not** adopt PydanticAI, smolagents, Mirascope, AutoGen, Marvin, Microsoft Agent Framework, or similar libraries as the system's core runtime or orchestration layer.

### Decision boundaries / non-goals

This ADR decides **runtime ownership only**. It does **not** choose the event transport model (D3), the agent persistence topology (D5), or the LLM interface strategy (D2).

A dependency counts as a **supporting dependency** only if it stays behind TeamAutobot-owned interfaces and does **not** own any of the following:

- task scheduling or task-graph execution flow
- agent lifecycle semantics or pooling behavior
- event schemas, event semantics, or correlation model
- working-memory/session-context model
- orchestration flow between agents, tools, and review loops

Litmus test: if removing the dependency would require redesigning TeamAutobot's orchestration concepts rather than swapping an adapter, then that dependency is acting as an **owning runtime** and falls outside this proposal.

Stateful agents in this ADR means TeamBot v2 agents have durable runtime semantics and context boundaries. It does **not** imply a decision yet on whether agents are long-lived processes, spawned per task, or use a hybrid topology; that remains D5.

Similarly, event ownership here means TeamBot v2 owns its event model and runtime abstraction. It does **not** decide whether transport is in-process, file-backed, broker-based, or otherwise; that remains D3.

## Consequences

This keeps the architecture aligned with the v2 design principles. TeamAutobot retains full control over agent identity, event semantics, replay behavior, dynamic fan-out, and observability. The runtime stays understandable because the key orchestration logic lives in this repository rather than inside framework abstractions.

The trade-off is increased engineering responsibility. We must implement the agent loop, lifecycle management, tool invocation boundaries, retries, and tracing ourselves. That also means we need stronger tests around replayability, failure handling, and concurrency limits than a framework-backed approach might initially require.

This decision does **not** prohibit the use of libraries for narrow concerns. It only rejects handing the system's central control model to an external agent framework.

## Alternatives Considered

### Comparison matrix

Indicative fit against TeamBot v2's D1 decision drivers:

| Option | Lifecycle control | Replayability fit | Event ownership | Dynamic fan-out fit | Coupling risk |
|--------|-------------------|-------------------|-----------------|---------------------|---------------|
| Custom runtime | High | High | Repo-owned | High | Low |
| PydanticAI | Medium-high | Medium | Mostly repo-owned with custom wiring | Medium | Medium |
| Microsoft Agent Framework | Medium | High | Framework-shaped | Medium | High |
| AutoGen | Medium | Medium | Framework-shaped | Medium | High |

This matrix is intentionally qualitative. It is meant to compare architectural fit for D1, not to judge overall framework quality.

### Use PydanticAI as the core runtime

PydanticAI was the strongest lightweight candidate because it emphasizes type safety, structured outputs, and observability. It is relatively low-opinionation compared to larger agent frameworks.

It was not chosen as the core runtime because TeamAutobot still needs to own the hard parts that matter most here: dynamic task graphs, event-driven coordination, replayability, agent pooling, and lifecycle control. Using PydanticAI as the foundation would reduce some boilerplate, but it would not remove the need to build the orchestration model ourselves, while still introducing framework coupling.

### Use AutoGen as the core runtime

AutoGen is a legitimate comparison point because it helped define modern multi-agent patterns and includes an event-driven core plus higher-level team abstractions. It is especially relevant to TeamAutobot because our design also cares about agent collaboration, tool use, and coordination patterns rather than just single-agent prompting.

It is not the leading direction for TeamAutobot because it still represents adopting a framework-owned runtime model, and Microsoft's current guidance points evaluators toward Microsoft Agent Framework as the newer comparison target in that ecosystem. That leaves AutoGen valuable as prior art and a reference point, but weaker as the main foundation to choose today.

### Use Microsoft Agent Framework as the core runtime

Microsoft Agent Framework is a serious candidate and should be considered explicitly in this ADR. It brings first-party support for agents, tools, sessions/state, middleware, events, checkpointing, and graph-based workflow orchestration. It is especially relevant because TeamAutobot also needs multi-agent coordination, observability, and resumability.

It is not the leading direction at the moment because its strengths come bundled with a stronger runtime model than TeamAutobot currently wants to adopt. Its workflow and orchestration concepts are powerful, but they pull the design toward framework-owned execution semantics rather than a repo-owned runtime made of smaller primitives. That may be a good trade in some systems, but for TeamAutobot it risks narrowing how we model task graphs, agent pooling, and event semantics before we have validated our own core abstractions.

This does **not** rule it out permanently. It means the ADR should treat it as a first-class alternative that needs explicit comparison, especially if the custom runtime proves too costly or if we decide the benefits of built-in workflow infrastructure outweigh the architectural constraints.

### Use another lightweight library as the core runtime

smolagents and Mirascope were considered as lighter-weight options, but they appear better suited to prototyping or simpler orchestration patterns than to a deeply observable, replayable engineering runtime. Marvin appears stronger operationally, but is more opinionated and moves closer to the class of framework the design intentionally avoids. AutoGen and Microsoft Agent Framework are stronger than these options for orchestration, but for the same reason they are also more substantial and more architecture-shaping.

These options were rejected because they either provide too little structure where TeamAutobot needs reliability, or too much structure where TeamAutobot needs freedom.

### Revisit a heavier agent framework

This remains ruled out for frameworks such as LangGraph and CrewAI. Frameworks that impose state machines, handoff models, or workflow shapes too early are misaligned with the intended architecture. AutoGen is treated separately above because of its historical importance and because Microsoft's own current direction now points toward Microsoft Agent Framework.

## Follow-up Actions

- Define the minimum viable custom runtime surface for Phase 1:
  - agent loop
  - agent pool
  - tool registry
  - memory/session boundary manager
  - event bus abstraction
- Create a thin internal interface for LLM clients so D2 can be decided independently of D1.
- Build a Phase 1 spike that proves one agent can receive a task, call a tool, emit events, and persist an artifact.
- Add replay- and lifecycle-focused tests early so the custom runtime stays reliable as concurrency increases.
- Allow comparison spikes with lightweight libraries only if they are isolated and do not become hidden architectural dependencies.
- If D1 remains contentious, add a short explicit comparison appendix or follow-on ADR comparing the custom runtime approach directly against Microsoft Agent Framework, AutoGen, and PydanticAI.

## Notes

This decision favors long-term architectural fit over short-term implementation speed. It was moved to `Accepted` after explicit repository-owner approval. If later evidence shows the custom runtime is disproportionately costly, the project can introduce narrow helper dependencies without surrendering control of the runtime itself.
