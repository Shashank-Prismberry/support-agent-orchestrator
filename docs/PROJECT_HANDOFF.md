# Support Agent Orchestrator — Project Handoff

**Snapshot date:** 2026-11-27  
**Purpose:** Self-contained status and continuation guide for a new coding agent.

## A. Project overview

This repository contains an independent orchestration service for a multi-tenant B2B customer-support product. It classifies and routes requests, coordinates specialist agents, and is intended to integrate with Backend APIs, MCP, RAG, and LLM providers. The Backend remains authoritative for authentication, authorization, business records, audit records, and business side effects.

The intended stack is Python 3.12, LangGraph, FastAPI/SSE, Pydantic Settings, SQLAlchemy async, PostgreSQL, Alembic, uv, pytest, and Ruff. Actual dependencies and implemented entry points are in `pyproject.toml` and `src/`.

The repository uses Ports and Adapters. Important directories:

- `src/support_agent_orchestrator/domain/` — typed domain contracts and state.
- `src/support_agent_orchestrator/ports/` — provider-independent interfaces.
- `src/support_agent_orchestrator/application/` — application services and node behavior.
- `src/support_agent_orchestrator/graph/` — central LangGraph construction.
- `src/support_agent_orchestrator/infrastructure/` — PostgreSQL and adapters.
- `migrations/` — Agent-owned Alembic history.
- `tests/unit/` and `tests/integration/` — isolated and PostgreSQL-backed tests.
- `support_ai-backend/` — a separate, pre-existing Backend working tree. It is outside this Agent's ownership and was not changed during closeout.

There is not yet a FastAPI app, API transport, worker process, or runnable service entry point. The `api/` and `agents/` packages do not constitute a deployed API/worker implementation.

## B. Current implementation status

Official AGT names and order below are unchanged. ORCH labels remain proposed workstreams, not official AGT IDs.

| Work | Status | Main files/tests | Remaining work |
|---|---|---|---|
| AGT-1.1 — LangGraph State & Supervisor Node | Implemented; covered by full suite | `domain/state.py`, `domain/context.py`, `application/supervisor.py`, `ports/routing.py`, `graph/workflow.py`; `test_state.py`, `test_supervisor.py`, `test_workflow.py` | Preserve regression coverage. |
| AGT-1.2 — Specialized Sub-Agent Nodes | Implemented; covered by full suite | `application/specialists.py`, `application/prompts.py`, `ports/agents.py`; `test_specialists.py`, `test_specialist_workflow.py` | External capabilities are not wired. |
| AGT-2.1 — RAG & MCP Tool Wiring | Not started as an official deliverable | Shared RAG boundary exists in `application/knowledge.py`, `domain/knowledge.py`, and `ports/knowledge.py`; `test_knowledge_retrieval.py` | Implement approved RAG/MCP adapters and allowlists after service contracts are confirmed. No external RAG/MCP adapter is present. |
| AGT-3.1 — Human-in-the-Loop (HITL) Refund Gate | Not started | No checkpoint/resume implementation | Requires the shared refund approval flow, approved checkpointing, and durable recovery. Never invoke a refund requiring approval before the workflow is implemented. |
| AGT-3.2 — Graceful RBAC Refusal Handling | Not started | No complete transport/error integration | Implement safe Backend/MCP permission error handling after integration. |
| AGT-4.1 — Adversarial Red-Teaming Suite | Not started | Existing unit tests cover component behavior, not the complete adversarial suite | Add cross-tenant, prompt-injection, capability, and approval-boundary tests. |
| AGT-4.2 — Interactive Demo UI | Not started | No UI | Choose the approved UI approach when this deliverable starts. |
| ORCH-P1 — Request Analysis and Mode Routing (proposed) | Implemented; covered by full suite | `domain/request_analysis.py`, `ports/analysis.py`, `application/request_analysis.py`, `graph/workflow.py`; `test_request_analysis.py`, `test_request_analyzer_port.py` | Evaluate classification quality with a real approved Analyzer provider. |
| ORCH-P2 — Deep Planning and Plan Validation (proposed) | Implemented; covered by full suite | `domain/planning.py`, `ports/planning.py`, `application/planning.py`, `graph/workflow.py`; `test_plan_validation.py`, `test_planning*.py` | Deep currently stops after a validated plan. It does not run tasks. |
| ORCH-P3 — Workflow Execution and Specialist Task Contract (proposed) | Not started | No scheduler or worker | Design/implement separately; not an official AGT prerequisite unless formally approved. |
| ORCH-P4 — Aggregation and Reliability (proposed) | Not started | No task-result aggregator | Design/implement separately; include partial failure, retries, deadlines, and recovery. |
| Agent PostgreSQL acceptance foundation (no official AGT ID) | Implemented and locally integration-tested | `domain/acceptance.py`, `ports/acceptance.py`, `application/acceptance.py`, `infrastructure/acceptance.py`, `infrastructure/acceptance_tables.py`, `infrastructure/database.py`, `infrastructure/migrations.py`, `config/settings.py`, `migrations/env.py` | This is not job dispatch, a worker, checkpointing, SSE persistence, or the full memory system. |

Closeout verification on this snapshot: PostgreSQL integration suite **18 passed**; complete suite **349 passed**; Ruff check and formatting passed for Orchestrator source/tests/migrations; `uv lock --check` passed.

## C. Architecture and approved decisions

- Ports and Adapters; graph/application code depends on provider-independent interfaces.
- Backend owns authentication, identity, tenant/RBAC decisions, business data, audit logs, and business effects. The Agent must not query Backend tables directly.
- One PostgreSQL server hosts separate databases: Backend `support_ai_db`; Agent `orchestrator_db`. Agent persistence belongs in `orchestrator_db.orchestrator` only.
- Backend/MCP remains authoritative for business operations and permissions. RAG is a separate external service, not MCP; retrieval uses the shared `KnowledgeRetriever` boundary and `retrieve_kb(query, limit=5)` contract.
- The six MCP tools remain exactly `get_ticket_details`, `search_tickets`, `create_ticket`, `update_ticket_status`, `add_internal_note`, and `issue_refund`. No MCP adapter is implemented.
- `AgentState` remains exactly `messages`, `user_context`, `active_agent`, and `approval_status`.
- Conversational requests use a lightweight response route. Quick and Context use Analyzer → Supervisor → exactly one specialist. Deep currently produces a validated plan only; no scheduler/task execution/aggregation exists.
- One active execution per trusted conversation scope is enforced by the acceptance adapter using a transaction-scoped PostgreSQL advisory lock. `user_id`, `conversation_id`, and LangGraph `thread_id` remain distinct.
- Atomic request acceptance persists one inbound session message, one accepted execution, one scoped idempotency record, and dispatch eligibility transactionally. Request IDs are supplied by the caller; the Agent does not invent them.
- The memory architecture has three conceptual tiers: Company Memory through external RAG; Account Memory scoped by `(org_id, user_id)`; Session Memory scoped by conversation/thread. Persistent memory retrieval/storage and Context Assembly are not implemented. The acceptance `session_messages` table is only an inbound-turn persistence foundation, not a complete memory system.
- Approved Context Assembly design distinguishes sanitized Analyzer context loaded before classification from Specialist context selected after routing. The latter is not a wholesale copy of Analyzer input. Quick defaults to the current request plus relevant eligible Company Memory; Context can use relevant Session Memory, eligible confirmed Account preferences, and relevant Company Memory. Conversational and the current plan-only Deep route do no post-analysis memory retrieval. Triage and Billing can receive supplied Company Memory passages but cannot invoke RAG independently; Knowledge uses the shared retrieval boundary.
- Initial Account Memory is restricted to explicit, non-sensitive, user-confirmed preferences. Inferred profiles, support-history patterns, Backend-owned facts, and authorization data are excluded.
- Inbound request idempotency uses a caller-supplied stable request ID scoped by trusted organization/user/conversation and a versioned canonical payload fingerprint (currently implementation version 1). Same-key/same-payload returns the original execution; same-key/different-payload conflicts without changing the original record. This does not establish exactly-once behavior for external services; operation-level idempotency/reconciliation remains future work.
- Checkpoints are separate from session-message and memory persistence. No LangGraph PostgreSQL checkpointer dependency or implementation is present.
- Refunds over `$100.00` require the shared explicit Org_Admin approval workflow. Backend owns approval enforcement/token creation and consumption; AGT-3.1 owns interrupt/checkpoint/approval/resume. Never substitute a local approval system.
- The embedding dimension mismatch remains unresolved: shared `docs/CONTRACTS.md` specifies `VECTOR(384)` with `all-MiniLM-L6-v2`, while the integration companion specifies `text-embedding-3-small` at 1536 dimensions. Neither contract was changed.

### Current vs future

Implemented: four-mode request analysis/routing, plan-only Deep planner and validation, specialist context bounds, provider-independent RAG retrieval boundary, atomic PostgreSQL request acceptance, Alembic migration, environment configuration, and unit/integration tests.

Designed but not implemented: API/worker split, authenticated Backend API integration, external MCP/RAG adapters, durable job dispatch/leases, LangGraph checkpointing, SSE status/event persistence, full Context Assembly, Session summaries/compaction/retrieval, Account Preference persistence, and full memory lifecycle.

## D. Database architecture and current state

### Ownership and connection

- PostgreSQL server: existing Backend server; user-verified mapping is host `localhost:5433` to container port `5432` (`support_ai_postgres`, PostgreSQL 16).
- Backend database: `support_ai_db`; Backend owns it. The Orchestrator must never connect to it.
- Agent database: `orchestrator_db`; owner/runtime/migration role: `orchestrator_user`.
- Agent schema: `orchestrator`, owned by `orchestrator_user`.
- Native PostgreSQL on the host may use port `5432`; Docker-published host access for the shared server is `localhost:5433`. Backend containers use their Compose service hostname on container port `5432`.
- Runtime, migration, and integration URLs are separate variables in the ignored root `.env`. Their passwords are not part of this document.

### Applied migration and objects

Alembic revision `20261126_01` is applied. The Alembic version table is `orchestrator.alembic_version` and stores revision `20261126_01`.

- `orchestrator.session_messages`: `message_id` UUID primary key; global identity `message_order`; `org_id`, `user_id`, `conversation_id`, `content`, and `created_at`. Named constraints: `pk_session_messages`, `uq_session_messages_message_order`, `uq_session_messages_scope_identity`.
- `orchestrator.executions`: `execution_id` UUID primary key; trusted scope columns; `status`; `dispatch_eligible`; `created_at`. Named constraints: `pk_executions`, `uq_executions_scope_identity`, `ck_executions_lifecycle_state`. Approved states are `accepted`, `running`, `waiting_for_approval`, `completed`, `failed`, `cancellation_requested`, and `cancelled`.
- `orchestrator.idempotency_records`: scope plus caller `request_id`, execution/message references, fingerprint version and SHA-256 fingerprint, timestamp. Named constraints: scoped primary key `pk_idempotency_records`, `ck_idempotency_fingerprint_version`, `ck_idempotency_fingerprint_length`, and scope-matching foreign keys `fk_idempotency_execution_scope` and `fk_idempotency_message_scope` (`ON DELETE RESTRICT`).

Primary-key and unique constraints have PostgreSQL backing indexes. The migration defines no standalone indexes. The initial migration creates no Backend objects and no tables in `public`; the Orchestrator role's public-schema permissions were not changed by closeout. The integration suite left zero executions in its generated `acceptance-%` test namespace after completion.

The migration failure root cause was an autobegun transaction from preflight `SELECT`s being passed to Alembic. Closing the connection rolled back migration DDL. `validate_migration_connection()` now rolls back the read-only preflight transaction before Alembic configures its migration transaction. A unit test covers this boundary; integration setup asserts the applied revision so a successful-but-empty migration cannot silently pass the suite.

### Migration and test commands

```bash
uv run alembic history
uv run alembic current
uv run alembic upgrade head
uv run pytest tests/integration/test_postgres_acceptance_integration.py -v
```

Online Alembic validates the database name and `orchestrator` schema before migration. `offline` SQL generation is disabled. Always verify the recorded revision after an upgrade. Do not use `downgrade` for routine recovery.

The integration tests require the migration first and write/delete only generated acceptance records. They are skipped when `TEST_DATABASE_URL` is missing. In this local environment `.env` contains the test URL, so `uv run pytest` runs live PostgreSQL integration tests as part of the full suite.

`support_ai_db` was not connected to or queried during closeout. The migration URL validator rejects that database, and the migration DDL is schema-qualified to `orchestrator`.

## E. Local development setup

Python requirement is `>=3.12,<3.13`. uv manages the environment and lockfile.

```bash
uv sync
source .venv/bin/activate
```

If the ignored root `.env` is absent, create it without overwriting an existing file:

```bash
cp -n .env.example .env
chmod 600 .env
```

Set local `DATABASE_URL` and `AGENT_MIGRATION_DATABASE_URL`. To opt into PostgreSQL tests, also set `TEST_DATABASE_URL` using `.env.test.example`. Use the existing local server at `localhost:5433`, database `orchestrator_db`, and URL-encode any special characters in the password. Never copy a real URL to an example or tracked file. Exported shell variables override `.env`.

Commands:

```bash
uv run pytest tests/unit
uv run pytest tests/integration/test_postgres_acceptance_integration.py -v
uv run pytest
uv run ruff check src tests migrations
uv run ruff format --check src tests migrations
uv run alembic current
uv run alembic history
uv run alembic upgrade head
```

Run the PostgreSQL suite serially; do not add parallel execution against the shared test database. Do not run Backend containers, migrations, or seeds as part of routine Agent work. There is currently no application startup command because the API and worker entry points do not exist.

## F. Prioritized outstanding work

1. **AGT-2.1:** Confirm remaining MCP transport/auth lifecycle and RAG authentication/context propagation with owners; implement the external adapters, explicit registration/allowlists, shared error mapping, and tests. Keep RAG external and preserve the `retrieve_kb` boundary.
2. **Persistence/recovery foundation:** Design and implement durable job claims/leases and PostgreSQL LangGraph checkpointing, including sensitive-data, retention/deletion, access, and recovery policies. Verify checkpointer API before adding a dependency or configuration.
3. **AGT-3.1:** Implement LangGraph interrupt/approval/rejection/resume for protected refunds only after the persistence foundation and Backend approval flow are ready.
4. **AGT-3.2:** Implement safe permission-denial/refusal mapping once Backend/MCP errors are integrated.
5. **AGT-4.1:** Build adversarial tests across the approved personas, tenant boundaries, untrusted content, tool access, and approval rules.
6. **AGT-4.2:** Implement the approved interactive demo UI with authenticated identity flow and safe approval controls.
7. **ORCH-P3/P4 (proposed, not official):** Separately design task execution/scheduling, aggregation, and reliability. Do not treat them as official AGT prerequisites absent formal approval.
8. **Three-tier memory (deferred):** Implement Session/Account Memory and Context Assembly only after lifecycle/privacy/storage decisions are approved. Initial Account Memory scope is explicit, non-sensitive, user-confirmed preferences only.

External approvals still needed include RAG authentication/context propagation; MCP transport/error behavior and final allowlists; Backend/API inbound idempotency identity contract; Product retention/cancellation policies; and checkpoint/recovery policies. Preserve all owner boundaries described in `docs/CONTRACTS.md`.

## G. Known issues and risks

- No API, worker, queue/job claim loop, SSE endpoints, or runnable service entry point exists.
- No LangGraph checkpointer or durable job recovery exists; AGT-3.1 cannot rely on persistence yet.
- MCP and external RAG adapters are absent; Backend/RAG integrations remain design boundaries only.
- Current session message ordering is a global identity, not a per-conversation chronological sequence. Full Session Memory is not implemented.
- The role's effective `public` schema privileges were not changed in this workstream; do not assume they are absent. Keep all Agent DDL explicitly in `orchestrator` and coordinate any privilege changes with the database owner.
- The shared-contract 384-dimensional embedding and integration-contract 1536-dimensional embedding conflict remains unresolved; ask the RAG/integration owner before changing either.
- Retention, deletion, checkpoint content, and memory lifecycle policies are not implemented.
- The root `.env` is local and ignored, mode `600`; do not expose or transfer it. The example files contain placeholders.
- Closeout did not access `support_ai_db`; Backend data was not inspected or changed.

## H. Instructions for the next coding agent

Read in this order: `AGENTS.md`, `docs/CONTRACTS.md`, `IMPLEMENTATION_PLAN.md`, `INTEGRATION_CONTRACT.md`, `docs/ORCHESTRATION_DESIGN.md`, `DELIVERABLE_MAPPING.md`, `PROGRESS.md`, then the source/test files for the task. `docs/CONTRACTS.md` is the locked shared authority; do not modify it. Preserve official AGT task names/order and label ORCH work as proposed.

Keep `AgentState` at four fields. Never query Backend business tables or RAG tables directly. Do not treat Pydantic validation or memory as authentication/authorization. Never put credentials in prompts, state, checkpoints, logs, examples, or handoff documents. Do not fabricate tools/endpoints or refund approvals. Use `orchestrator_db.orchestrator` only for Agent persistence. Inspect working-tree changes before editing and preserve user changes. Use focused tests, the full suite when appropriate, and Ruff. The user controls every Git mutation.

Before extending persistence, inspect the current acceptance entities and adapter. Keep request idempotency, operation idempotency, execution state, checkpoints, and memory as distinct concerns. Do not claim PostgreSQL semantics from fake tests; use the real PostgreSQL integration tests when required.

## I. Exact handoff snapshot

- Branch: `main`.
- Latest commit at closeout start: `65431af` (`Merge pull request #5 from Shashank-Prismberry/feature/orch-p2-deep-planner`). No Git mutations were performed.
- Alembic revision: `20261126_01`.
- Tests: focused PostgreSQL integration **18 passed**; full suite **349 passed**, no skips/failures in that run.
- Ruff: check and format passed for `src`, `tests`, `migrations`.
- Lockfile: `uv lock --check` passed.
- Root `.env`: present, Git-ignored, mode `600`; contents intentionally not included.
- Working tree: `main` is still at `65431af` (`Merge pull request #5 from Shashank-Prismberry/feature/orch-p2-deep-planner`); no Git mutations were performed. All changes below remain uncommitted.
- Modified tracked files: `.github/copilot-instructions.md`, `.gitignore`, `COPILOT_MASTER_PROMPT.md`, `DELIVERABLE_MAPPING.md`, `IMPLEMENTATION_PLAN.md`, `INTEGRATION_CONTRACT.md`, `PROGRESS.md`, `README.md`, `docs/README.md`, `pyproject.toml`, `tests/conftest.py`, `uv.lock`.
- Untracked Agent/project files: `.env.example`, `.env.test.example`, `alembic.ini`, `docs/PROJECT_HANDOFF.md`, `migrations/` (including the initial revision), acceptance/config/database source files under `src/support_agent_orchestrator/`, `tests/integration/test_postgres_acceptance_integration.py`, and the PostgreSQL configuration/acceptance unit tests under `tests/unit/`.
- The pre-existing untracked `support_ai-backend/` working tree was preserved and not changed. The pre-existing modified files and untracked Orchestrator foundation observed at closeout start were preserved; the items listed above are the final status snapshot.
- A temporary preflight helper from earlier work exists outside the repository at `/tmp/orchestrator_db_preflight.py`; it is not required for project operation. A temporary uv cache directory may also exist under `/tmp/support-agent-uv-cache`.
