# Project Progress --- Support Agent Orchestrator

**Last updated:** 2026-11-24\
**Overall status:** AGT-1.2 complete; AGT-2.1 not started\
**Current phase:** Official deliverables\
**Current official deliverable:** AGT-2.1 --- RAG & MCP Tool Wiring
(not started)

## Decisions established

-   Independent Agent Orchestrator service.
-   Frontend -\> Backend -\> Agent; Backend proxies SSE.
-   Separate API and worker processes/containers.
-   PostgreSQL-backed job dispatch initially; no Redis initially.
-   Database `support_ai_db`; Backend schema `public`; Agent schema
    `orchestrator`.
-   Backend provisions `orchestrator`; Agent independently manages its
    schema migrations/checkpointer.
-   Business data only through authenticated Backend APIs and MCP.
-   Hexagonal Architecture and replaceable ports/adapters.
-   Central Supervisor with Triage, Knowledge and Billing agents.
-   SSE initially, persisted event replay/reconnection; disconnect does
    not cancel workflow.
-   One active execution per conversation; one persistent LangGraph
    thread per conversation initially.
-   Keep `user_id`, `conversation_id`, `thread_id` distinct.
-   Groq first, NVIDIA NIM second, Mistral later if API access permits;
    one model initially.
-   Full memory implementation deferred until official tasks complete.
-   Docker from the beginning.
-   Python 3.12, uv, Ruff, pytest, Pydantic Settings.
-   User controls commits and pushes.

## Workspace actions reported

-   Local project folder created.
-   Folder opened in ChatGPT Codex local environment.
-   Root `AGENTS.md` created.
-   AGT-1.1 implemented and verified: typed graph state, trusted user
    context, provider-independent Supervisor router, terminal routing
    graph and unit tests.
-   AGT-1.1 security remediation verified: immutable trusted context,
    internal graph-input boundary, metadata-free routing input and
    credential sanitization.
-   Final AGT-1.1 security fixes verified: controlled graph-input
    construction, server-owned message identifiers, and provider-error
    exception isolation.
-   AGT-1.2 implemented and verified: async injected specialist nodes,
    role-only prompts, sanitized generation requests, safe failures, and
    Supervisor-to-specialist-to-END integration.
-   AGT-1.2 review hardening verified: JSON-delimited role metadata,
    explicit specialist state validation, and strict specialist mapping
    validation.
-   AGT-1.2 invocation contract verified: legacy graphs retain sync
    invocation, specialist-enabled graphs reject sync calls with a clear
    async-only error, and async invocation remains available.

## Not yet confirmed / not done

-   Git initialization, GitHub remote and branch state.
-   Dockerfiles and Compose setup.
-   Live integration with Backend, MCP or RAG.

Do not mark work complete unless actually done and verified.

## Official deliverables

  ID        Deliverable                            Status
  --------- -------------------------------------- -------------
  AGT-1.1   LangGraph State & Supervisor Node      Complete (44 tests, 100% coverage)
  AGT-1.2   Specialized Sub-Agent Nodes            Complete (62 tests, 100% coverage)
  AGT-2.1   RAG & MCP Tool Wiring                  Not started
  AGT-3.1   Human-in-the-Loop (HITL) Refund Gate   Not started
  AGT-3.2   Graceful RBAC Refusal Handling         Not started
  AGT-4.1   Adversarial Red-Teaming Suite          Not started
  AGT-4.2   Interactive Demo UI                    Not started

## Immediate next steps

1.  Review AGT-1.2 and commit manually.
2.  Preserve canonical `docs/CONTRACTS.md` v3.0 unchanged.
3.  Begin AGT-2.1 after approval.

## Update rule

For each completed deliverable record implementation summary, changed
files, tests actually run/results, integration blockers and suggested
commit message. User commits manually.
