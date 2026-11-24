# Support Agent Orchestrator --- Implementation Plan

**Status:** Architecture baseline agreed; implementation not yet
started\
**Python:** 3.12 (`>=3.12,<3.13`)\
**Repository:** `support-agent-orchestrator`

## 1. Purpose and scope

Build an independently deployed Agent Orchestrator service for a
multi-tenant B2B customer-support application. It coordinates LangGraph
agents, integrates with Backend/MCP/RAG/LLM services, handles HITL
workflows, and exposes HTTP/SSE interfaces to Backend.

The Agent service does **not** own business records such as customers,
tickets, invoices, official ticket messages, staff notes or business
audit logs. Those remain Backend-owned.

Official deliverables, in order: 1. AGT-1.1 --- LangGraph State &
Supervisor Node 2. AGT-1.2 --- Specialized Sub-Agent Nodes 3. AGT-2.1
--- RAG & MCP Tool Wiring 4. AGT-3.1 --- Human-in-the-Loop (HITL) Refund
Gate 5. AGT-3.2 --- Graceful RBAC Refusal Handling 6. AGT-4.1 ---
Adversarial Red-Teaming Suite 7. AGT-4.2 --- Interactive Demo UI

Preserve official IDs, names and order. Full account-memory
extraction/retrieval, summaries and compaction are deferred until these
deliverables are complete. Do not expand initial scope prematurely.

## 2. System and deployment architecture

The Agent Orchestrator is an independent Python service. The application
request path is:

``` text
Frontend -> Backend API/Gateway -> Agent Orchestrator
                                      |
                                      +-> Backend REST APIs
                                      +-> MCP server
                                      +-> RAG service
                                      +-> LLM provider
```

The frontend communicates through Backend. Backend forwards
authenticated requests and proxies SSE without buffering.

Run API and workflow execution separately: - **API process:** request
validation, auth integration, workflow submission, status and SSE
endpoints. - **Worker process:** claims durable jobs and executes
LangGraph workflows. - **PostgreSQL:** jobs, checkpoints and Agent-owned
operational persistence.

Start with PostgreSQL-backed job dispatch. Do not add Redis or another
broker without a demonstrated need and approved design. API and worker
coordination must not depend on process-local booleans or in-memory
queues.

## 3. Architecture and agent topology

Use Hexagonal Architecture (Ports and Adapters): - Keep core
orchestration independent of infrastructure. - Define ports separately
from adapter implementations. - Use dependency injection and
configuration-based adapter selection. - Keep FastAPI replaceable; keep
the LangGraph graph independently invokable/testable. - Use
local/in-memory adapters while external services are unavailable. -
Avoid premature abstractions.

Initial graph: central Supervisor routes to Triage, Knowledge and
Billing specialist agents. The central graph controls state,
transitions, interruptions and completion. Specialists must not freely
invoke one another. No individual subgraphs initially unless approved
later.

Official initial `AgentState` fields include `messages`, `user_context`,
`active_agent`, `approval_status`. Add other typed fields only when
justified. Never put raw JWTs, credentials or secrets in graph state or
prompts.

## 4. Conversation, execution and streaming

Keep identifiers distinct: - `user_id`: authenticated identity. -
`conversation_id`: ongoing chat. - `thread_id`: LangGraph checkpoint
thread.

Initially, one persistent `thread_id` maps to one `conversation_id`.
Allow only one active execution per conversation; reject new messages
while processing or waiting for approval. Enforce this
durably/atomically across API and worker processes.

A workflow execution's terminal state does not close the conversation.
After completion, failure or cancellation, the conversation can accept
another message unless archived/deleted.

Streaming is preferred; synchronous execution remains supported. SSE is
the initial transport. The graph must not depend on FastAPI or SSE.

### Event model

Workflow lifecycle events: - `workflow.started` - `supervisor.routed` -
`agent.started` - `agent.completed` - `tool.started` -
`tool.completed` - `approval.required` - `workflow.completed` -
`workflow.failed`

Assistant response events: - `response.started` - `response.token` -
`response.completed`

Use a common versioned event envelope with event ID, conversation ID,
type, timestamp and validated payload. Persist events and support replay
with event IDs / `Last-Event-ID`; replay missed events before continuing
live delivery. Enforce authorization for replay. Never expose hidden
reasoning, credentials, raw prompts or sensitive tool payloads.

An SSE disconnect does not cancel workflow execution. Reconnection
resumes delivery for the same conversation. Manual archive/restore is
planned; archived conversations cannot receive messages until restored.
Do not archive while processing or awaiting approval. Detailed
deletion/retention policy can be decided when required.

Workflow status (e.g. `processing`, `waiting_for_approval`, `completed`,
`failed`, `cancelled`) is separate from conversation lifecycle
(`active`, `archived`, `deleted`).

## 5. Failures, retries, timeouts and cancellation

Separate recoverable transient failures, non-recoverable failures
(including permission denial), and unexpected workflow failures. Retry
transient failures with bounded exponential backoff. Keep retries
primarily in adapters; orchestration owns workflow-level recovery. Do
not blindly retry side-effecting actions; use idempotency protections.

Timeouts are configurable and liberal enough for multi-agent workflows
and slower model/tool responses. Configure external operation timeouts
separately from overall workflow duration. A slow but active stream is
not stalled. Waiting for HITL approval does not consume the normal
execution timeout.

Support explicit cancellation. Cancellation prevents further work where
possible but cannot reverse an external side effect already completed.

## 6. Database and persistence ownership

Latest Backend confirmation supersedes the earlier two-logical-database
proposal:

-   PostgreSQL database: `support_ai_db`
-   Backend-owned schema: `public`
-   Agent-owned schema: `orchestrator`

Backend provisions `orchestrator` during database/Docker initialization.
Agent independently manages migrations and checkpoint setup inside that
schema. Backend Alembic is scoped to `public`.

Backend-provided local connection example:

``` env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/support_ai_db
```

These are local-development defaults only, not production credentials.

Agent-owned operational data may include LangGraph checkpoints/blobs,
workflow jobs, conversation records/ephemeral turns, persisted SSE
events, and (later) approved memory/summary records.

Business records remain Backend-owned. **Never query Backend business
tables directly through SQL.** Use authenticated Backend REST APIs and
agreed MCP tools so Backend enforces authorization, RLS, tenant
isolation and audit logging. Official ticket messages and private staff
notes are synchronized through Backend APIs.

Use `langgraph-checkpoint-postgres` for durable checkpointing. Verify
the installed Python package API before configuring the `orchestrator`
schema. If using PostgreSQL `search_path`, apply it reliably to every
relevant connection/session, including pooled connections; do not assume
an unsupported `schema` constructor parameter exists. Keep SQLAlchemy
application and checkpointer connection configuration explicit. The
application URL uses `asyncpg`; the checkpointer may require Psycopg
depending on the chosen API.

## 7. Authentication and security

`docs/CONTRACTS.md` (shared Team Contract v3.0) is authoritative: -
Accept and validate Backend-issued JWTs according to the contract. -
Obtain trusted context through the agreed Backend interface
(`GET /auth/me`). - Do not trust client-supplied roles, permissions or
tenant IDs. - Do not use account memories as authorization evidence. -
Never put raw JWTs/secrets into prompts or graph state. - Forward
credentials only to downstream services that require them. - Downstream
services remain authoritative for authorization, especially sensitive
operations. - Prevent cross-tenant leakage through state, memory,
retrieval, logs and event replay.

Do not independently redefine shared JWT fields, permissions, error
envelopes, identities or service contracts.

## 8. External integrations

**Backend:** authenticated REST APIs for identity/context and business
operations. Backend owns business rules, RLS, authorization and audit
logging.

**MCP:** use `langchain-mcp-adapters` as required by AGT-2.1. Canonical
tools in the shared contract include `get_ticket_details`,
`search_tickets`, `create_ticket`, `update_ticket_status`,
`add_internal_note`, `issue_refund`. Use exact schemas/transport/error
mapping from the contract; do not invent them.

**RAG:** Knowledge Agent uses a port and later HTTP adapter. Contract
operation: `retrieve_kb(query, limit=5)`. Result fields include
`document_id`, `chunk_index`, `title`, `content`, `access_level`,
`similarity_score`. RAG enforces tenant/access-level filtering. Shared
knowledge embedding contract is `text-embedding-3-small`, 1536
dimensions. Do not query RAG tables directly or build an independent
knowledge embedding pipeline.

**LLM:** provider-independent adapter. Initial preference: Groq first,
NVIDIA NIM second, Mistral later if suitable API access is available.
Start with one configurable model shared by Supervisor and specialists.
Verify each model's tool-calling, structured-output and streaming
capabilities. No hardcoded credentials.

## 9. Development stack

-   Python `>=3.12,<3.13`
-   `uv`, `pyproject.toml`, committed `uv.lock`, `.venv`
-   Pydantic Settings, `.env.example`, real `.env` ignored
-   Ruff for formatting/lint/import sorting
-   pytest, pytest-asyncio, pytest-cov
-   Docker and Docker Compose from the beginning
-   Standard-library `logging` with centralized configuration and
    structured logs

Run API and worker independently. Coordinate PostgreSQL with the team's
Compose provisioning; do not create conflicting database infrastructure.
GitHub Actions/CI is deferred; start with local checks.

## 10. Testing

Every feature includes tests for normal behavior, edge cases, invalid
input, failures, authorization/tenant-isolation assumptions, state
transitions and regressions. Mock Backend, MCP, RAG, LLM and external
infrastructure in unit tests. Separate unit and integration tests. Test
Supervisor, specialists, routing, state, ports/adapters and API/worker
behavior independently. Never claim tests passed unless executed.

## 11. Git and Codex workflow

User exclusively controls commits and pushes. Codex must never commit,
push, merge, rebase, amend, reset or rewrite Git history. It may inspect
`git status`, `git diff`, `git log`. Branch creation/switching requires
explicit instruction.

Work in coherent feature-sized batches, not micro-edits. At completion
report changed files, tests actually run/results, unresolved issues and
a suggested commit message.

Architecture changes require approval. Once a feature plan is approved,
implement the coherent feature and tests without repeated
micro-approvals. Explain dependencies before adding them. Ask before
security-sensitive changes.

## 12. Foundation sequence

Before AGT-1.1: 1. Confirm local Git/remote state. 2. Add/review project
documentation and Codex instructions. 3. Create `src/` package and tests
structure. 4. Configure Python/uv, Ruff, pytest and Pydantic Settings.
5. Establish Docker setup for API and worker, coordinated with shared
PostgreSQL. 6. Add centralized configuration/logging. 7. Run foundation
checks. 8. Start AGT-1.1.

Do not implement the entire memory system or every integration adapter
during foundation work.

## 13. Deferred decisions

Decide these when the relevant feature is reached: exact timeout/retry
values; full event payload schemas; job-claim/locking algorithm;
detailed retention/deletion policy; full memory implementation;
production autoscaling; CI; per-agent model selection; Redis or a
dedicated broker. Raise a decision when needed rather than inventing
one.
