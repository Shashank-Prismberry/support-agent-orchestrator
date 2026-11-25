# Support Agent Orchestrator — Current Implementation Notes

## Internal graph input boundary

The LangGraph wrapper accepts only `InternalGraphInput`, created with `create_internal_graph_input`. This validates and sanitizes the in-process contract; it does not authenticate callers. The API/worker boundary must authenticate the Backend-issued JWT and resolve trusted context through `GET /auth/me` before creating graph input. Do not treat Pydantic validation or `TrustedUserContext` construction as proof of authentication provenance.

## Current graph invocation contract

Legacy graphs built without injected specialists should use `OrchestrationGraph.invoke()` for reliable supported execution. They expose `await OrchestrationGraph.ainvoke()` for compatibility, but LangGraph 1.2.24 has a known process-lifecycle limitation when synchronous nodes are executed through that path. This is an upstream runtime limitation, not an application-level deadlock.

Graphs built with asynchronous specialist nodes are async-only: callers must use `ainvoke()`. Synchronous `invoke()` on those graphs raises `AsyncOnlyGraphError`; no event-loop bridging or synchronous adapter is used.

## Architecture evolution

The implementation currently completed for AGT-1.1 and AGT-1.2 is the Supervisor → one specialist → END baseline. The approved target architecture adds Request Analyzer and Quick/Context/Deep handling:
- Quick/Context continue through Supervisor → exactly one specialist.
- Deep will use Planner → validated plan → central workflow scheduler → specialist tasks → Aggregator.

The new architecture is a target design, not a claim that these components are already implemented. See `IMPLEMENTATION_PLAN.md` and `docs/ORCHESTRATION_DESIGN.md`.