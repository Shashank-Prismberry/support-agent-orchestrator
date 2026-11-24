# Copilot Master Prompt --- Support Agent Orchestrator

Use this as reusable project context for Copilot sessions. For ChatGPT
Codex, root `AGENTS.md` is the primary persistent instruction file.

## Read before substantial work

1.  `AGENTS.md`
2.  `IMPLEMENTATION_PLAN.md`
3.  `docs/CONTRACTS.md` (shared Team Contract v3.0; authoritative)
4.  `INTEGRATION_CONTRACT.md`
5.  `DELIVERABLE_MAPPING.md`
6.  `PROGRESS.md`

## Project

Build an independent Python 3.12 Agent Orchestrator service for a
multi-tenant B2B customer-support application. Stack: LangGraph,
FastAPI, PostgreSQL, Docker Compose, uv, Pydantic Settings, Ruff and
pytest.

## Agreed architecture

-   Frontend -\> Backend -\> Agent Orchestrator; Backend proxies
    HTTP/SSE.
-   Independent Agent service; separate API and worker
    processes/containers.
-   PostgreSQL-backed job dispatch initially; no Redis initially.
-   One database `support_ai_db`; Backend owns `public`, Agent owns
    `orchestrator`.
-   Backend provisions `orchestrator`; Agent manages its own
    migrations/checkpointer there.
-   Never query Backend business tables directly; use authenticated
    Backend REST APIs and MCP.
-   Hexagonal Architecture (Ports and Adapters), dependency injection,
    replaceable adapters.
-   Central LangGraph Supervisor with Triage, Knowledge and Billing
    agents; no individual subgraphs initially.
-   SSE initially; persist events and support replay/reconnection.
    Disconnect does not cancel workflow.
-   One active execution per conversation; initially one persistent
    LangGraph thread per conversation.
-   Keep `user_id`, `conversation_id`, `thread_id` distinct.
-   Groq first, NVIDIA NIM next, Mistral later if API access permits;
    one configured model shared initially.
-   Full memory implementation deferred until official AGT tasks are
    complete.
-   Docker from the beginning.
-   User exclusively controls Git commits/pushes.

## Official tasks --- preserve IDs, names and order

-   AGT-1.1 --- LangGraph State & Supervisor Node
-   AGT-1.2 --- Specialized Sub-Agent Nodes
-   AGT-2.1 --- RAG & MCP Tool Wiring
-   AGT-3.1 --- Human-in-the-Loop (HITL) Refund Gate
-   AGT-3.2 --- Graceful RBAC Refusal Handling
-   AGT-4.1 --- Adversarial Red-Teaming Suite
-   AGT-4.2 --- Interactive Demo UI

## Working rules

-   Inspect existing code and docs before changes; never overwrite
    blindly.
-   Ask before architecture changes and security-sensitive changes.
-   Explain why a new dependency is needed before adding it.
-   Once a feature plan is approved, implement the complete coherent
    feature and tests; do not stop after each file.
-   Add tests for happy paths, edge cases, invalid input, failure paths,
    permissions and tenant isolation.
-   Mock Backend/MCP/RAG/LLM in unit tests.
-   Never trust model/client-supplied identity, role, tenant or
    permissions.
-   Never put raw JWTs or secrets into prompts or graph state.
-   Never directly query Backend-owned business tables.
-   Do not implement unrelated or deferred scope.

## Git restrictions

Never commit, push, merge, rebase, amend, reset or rewrite history. Do
not create/switch branches unless explicitly instructed. User reviews
and commits manually.

At completion report changed files, tests actually run/results,
unresolved issues and suggested commit message. Do not claim unexecuted
tests passed.
