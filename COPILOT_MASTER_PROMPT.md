# Copilot Master Prompt — Support Agent Orchestrator

Use this as reusable project context for Copilot sessions. For ChatGPT Codex, root `AGENTS.md` is the primary persistent instruction file.

## Read before substantial work

1. `AGENTS.md`
2. `IMPLEMENTATION_PLAN.md`
3. `docs/CONTRACTS.md` (Shared Team Contract v3.0; authoritative and locked)
4. `INTEGRATION_CONTRACT.md`
5. `docs/ORCHESTRATION_DESIGN.md`
6. `DELIVERABLE_MAPPING.md`
7. `PROGRESS.md`

## Project

Build an independent Python 3.12 Agent Orchestrator service for a multi-tenant B2B customer-support application. Stack: LangGraph, FastAPI, PostgreSQL, Docker Compose, uv, Pydantic Settings, Ruff and pytest.

## Architecture

- Frontend → Backend → Agent Orchestrator; Backend proxies HTTP/SSE.
- Independent Agent service; separate API and worker processes/containers.
- PostgreSQL-backed job dispatch initially; no Redis initially.
- One database `support_ai_db`; Backend owns `public`, Agent owns `orchestrator`.
- Never query Backend business tables directly; use authenticated Backend REST APIs and agreed MCP tools.
- Hexagonal Architecture (Ports and Adapters), dependency injection and replaceable adapters.
- Central LangGraph workflow with Request Analyzer, Supervisor, Planner, Workflow Orchestrator, Triage/Knowledge/Billing specialists and Aggregator.
- Quick/Context: Analyzer → Supervisor → exactly one specialist.
- Deep: Analyzer → Planner → deterministic validation → central scheduler → specialist tasks → Aggregator.
- Specialists must not invoke one another. Central workflow owns multi-specialist coordination.
- Capability interfaces must be independent of MCP transport. Only six contract-defined MCP tools and `retrieve_kb` are currently in scope.
- Do not introduce individual specialist subgraphs initially.
- SSE initially; persist events and support replay/reconnection. Disconnect does not cancel workflow.
- One active execution per conversation; initially one persistent LangGraph thread per conversation.
- Keep `user_id`, `conversation_id`, `thread_id` distinct.
- Groq first, NVIDIA NIM next, Mistral later if API access permits; one configured model shared initially.
- Full memory implementation deferred until official AGT tasks are complete.
- User exclusively controls Git commits/pushes.

## Official tasks — preserve IDs, names and order

- AGT-1.1 — LangGraph State & Supervisor Node
- AGT-1.2 — Specialized Sub-Agent Nodes
- AGT-2.1 — RAG & MCP Tool Wiring
- AGT-3.1 — Human-in-the-Loop (HITL) Refund Gate
- AGT-3.2 — Graceful RBAC Refusal Handling
- AGT-4.1 — Adversarial Red-Teaming Suite
- AGT-4.2 — Interactive Demo UI

The orchestration extension is separately tracked as proposed ORCH-P1–P4 placeholders, not official AGT IDs, until the team assigns formal ownership/IDs.

## Capability limits and security

- Canonical MCP tools: `get_ticket_details`, `search_tickets`, `create_ticket`, `update_ticket_status`, `add_internal_note`, `issue_refund`.
- RAG operation: `retrieve_kb(query, limit=5)`.
- Do not invent invoice/payment lookup, reconciliation, note-read or other tools.
- Backend/MCP owns business authorization and side effects.
- RAG enforces tenant and authorized KB tier filters using trusted context.
- Never trust model/client-supplied identity, role, tenant or permissions.
- Never put raw JWTs or secrets into prompts, graph state, checkpoints or logs.
- Never directly query Backend-owned or RAG tables.
- `issue_refund` over `$100.00` requires the shared contract's HITL approval. AGT-3.1 owns interrupt/checkpoint/approval/resume. Never bypass it.

## Working rules

- Inspect existing code/docs before changes; never overwrite blindly.
- Treat `docs/CONTRACTS.md` as immutable and authoritative.
- Ask before materially different architecture/security changes.
- Explain why a new dependency is needed before adding it.
- Once a feature plan is approved, implement the complete coherent feature and tests; do not stop after each file.
- Add tests for happy paths, edge cases, invalid input, failures, permissions and tenant isolation.
- Mock Backend/MCP/RAG/LLM in unit tests.
- Validate all model-proposed plans deterministically.
- Do not implement unrelated or hypothetical capabilities.

## Git restrictions

Never commit, push, merge, rebase, amend, reset or rewrite history. Do not create/switch branches unless explicitly instructed. User reviews and commits manually.

At completion report changed files, tests actually run/results, unresolved issues and suggested commit message. Do not claim unexecuted tests passed.