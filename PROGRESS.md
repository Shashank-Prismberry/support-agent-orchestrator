# Project Progress --- Support Agent Orchestrator

**Last updated:** 2026-11-24\
**Overall status:** Architecture established; repository foundation in
preparation\
**Current phase:** Documentation / foundation\
**Current official deliverable:** AGT-1.1 --- LangGraph State &
Supervisor Node (not started)

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

## Not yet confirmed / not done

-   Git initialization, GitHub remote and branch state.
-   Source/test project scaffold.
-   `pyproject.toml`, `uv.lock`, Dockerfiles and Compose setup.
-   Application code and tests.
-   Any official AGT deliverable implementation.
-   Live integration with Backend, MCP or RAG.

Do not mark work complete unless actually done and verified.

## Official deliverables

  ID        Deliverable                            Status
  --------- -------------------------------------- -------------
  AGT-1.1   LangGraph State & Supervisor Node      Not started
  AGT-1.2   Specialized Sub-Agent Nodes            Not started
  AGT-2.1   RAG & MCP Tool Wiring                  Not started
  AGT-3.1   Human-in-the-Loop (HITL) Refund Gate   Not started
  AGT-3.2   Graceful RBAC Refusal Handling         Not started
  AGT-4.1   Adversarial Red-Teaming Suite          Not started
  AGT-4.2   Interactive Demo UI                    Not started

## Immediate next steps

1.  Add/review refreshed documentation.
2.  Preserve canonical `docs/CONTRACTS.md` v3.0 unchanged.
3.  Confirm Git/remote state without rewriting history.
4.  Create `src/` and tests structure.
5.  Configure uv, Ruff, pytest and Pydantic Settings.
6.  Establish Docker setup for API/worker coordinated with team
    PostgreSQL.
7.  Run foundation checks.
8.  Begin AGT-1.1.

## Update rule

For each completed deliverable record implementation summary, changed
files, tests actually run/results, integration blockers and suggested
commit message. User commits manually.
