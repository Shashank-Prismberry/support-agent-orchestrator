## Internal graph input boundary

The LangGraph wrapper accepts only `InternalGraphInput`, created with
`create_internal_graph_input`. This validates and sanitizes the in-process
contract; it does not authenticate callers. A future API/worker boundary must
authenticate the Backend-issued JWT and resolve trusted context through
`GET /auth/me` before creating graph input. Do not treat Pydantic validation
or `TrustedUserContext` construction as proof of authentication provenance.

Legacy graphs built without injected specialists should use
`OrchestrationGraph.invoke()` for reliable supported execution. They expose
`await OrchestrationGraph.ainvoke()` for compatibility, but LangGraph 1.2.24
has a known process-lifecycle limitation when synchronous nodes are executed
through that path. This is an upstream runtime limitation, not an
application-level deadlock.

Graphs built with asynchronous specialist nodes are async-only: callers must
use `ainvoke()`. Synchronous `invoke()` on those graphs raises
`AsyncOnlyGraphError`; no event-loop bridging or synchronous adapter is used.
