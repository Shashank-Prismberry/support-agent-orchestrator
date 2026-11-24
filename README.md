## Internal graph input boundary

The LangGraph wrapper accepts only `InternalGraphInput`, created with
`create_internal_graph_input`. This validates and sanitizes the in-process
contract; it does not authenticate callers. A future API/worker boundary must
authenticate the Backend-issued JWT and resolve trusted context through
`GET /auth/me` before creating graph input. Do not treat Pydantic validation
or `TrustedUserContext` construction as proof of authentication provenance.
