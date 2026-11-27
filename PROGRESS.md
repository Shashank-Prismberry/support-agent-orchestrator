# Project Progress — Support Agent Orchestrator

**Last updated:** 2026-11-27
**Overall status:** AGT-1.1 and AGT-1.2 complete; AGT-2.1 not started
**Current official deliverable:** AGT-2.1 — RAG & MCP Tool Wiring
**Architecture direction:** Conversational/Quick/Context/Deep workflow orchestration approved as a proposed project direction. ORCH-P1 and ORCH-P2 are implemented; ORCH-P3 and ORCH-P4 remain unstarted.

## Decisions established

- Independent Agent Orchestrator service.
- Frontend → Backend → Agent; Backend proxies SSE.
- Separate API and worker processes/containers.
- PostgreSQL-backed job dispatch initially; no Redis initially.
- One PostgreSQL server with separate databases: Backend owns `support_ai_db`; Agent owns `orchestrator_db.orchestrator`.
- A PostgreSQL administrator provisions `orchestrator_db.orchestrator`; Agent manages its schema migrations/checkpointer there.
- The Agent persistence foundation uses SQLAlchemy async with `asyncpg`, a separate Agent-owned Alembic history, explicit `orchestrator` targeting, and online migration target checks. Runtime and migration URLs are separate settings. The initial migration `20261126_01` is applied and verified in the local `orchestrator_db.orchestrator` database. Database/schema provisioning remains administrator-owned; local credentials remain only in the ignored root `.env`.
- Business data only through authenticated Backend APIs and agreed MCP tools.
- Hexagonal Architecture and replaceable ports/adapters.
- Central LangGraph workflow with Triage, Knowledge and Billing specialists.
- Specialists do not invoke one another; central workflow owns multi-specialist execution.
- Request Analyzer classifies Conversational/Quick/Context/Deep.
- Conversational messages use a lightweight response path with no Supervisor or specialist invocation.
- Quick/Context use Supervisor → exactly one specialist.
- Specialist generation includes bounded, sanitized Human/AI session history and excludes System/Tool messages.
- Deep currently uses Planner → validated plan and returns a plan-only result. Task execution, scheduling and aggregation are future proposed work.
- Capability layer is independent of MCP transport; only six contract-defined MCP tools and `retrieve_kb` are currently in scope.
- Backend/MCP authorization and tenant isolation remain authoritative.
- Refund approval requirements remain intact; AGT-3.1 owns HITL interrupt/checkpoint/approval/resume.
- SSE event replay/reconnection; disconnect does not cancel workflow.
- One active execution per conversation; one persistent LangGraph thread per conversation initially.
- Keep `user_id`, `conversation_id`, `thread_id` distinct.
- Three-tier memory architecture: Company memory through organization-scoped external RAG; Account memory scoped by `(org_id, user_id)` and deferred; Session memory scoped by conversation/thread. Context Assembly combines relevant sources without owning their storage.
- The provider-independent KnowledgeRetriever port and typed result contract are implemented. RAG remains a separate external service, not MCP; no external RAG adapter or authentication/endpoint behavior is implemented.
- Memory is not an identity, authorization, tenant-scope or permission source.
- Conversation state, workflow execution state, PostgreSQL checkpoints and long-term account memory remain conceptually separate.
- PostgreSQL checkpointing and durable job recovery are foundational requirements before AGT-3.1 relies on HITL interruption/resumption; this does not expand AGT-2.1 into persistence or full memory work.
- ORCH-P1 through ORCH-P4 remain proposed, separately tracked workstreams and are not mandatory prerequisites for AGT-3.1.
- Groq first, NVIDIA NIM second, Mistral later if API access permits; one model initially.
- Full memory implementation deferred until official tasks complete.
- Docker from the beginning.
- Python 3.12, uv, Ruff, pytest, Pydantic Settings.
- User controls commits and pushes.

## Workspace actions and completed work

- Local project folder created and opened in Codex local environment.
- Root `AGENTS.md` created.
- AGT-1.1 implemented and verified: typed graph state, trusted user context, provider-independent Supervisor router, terminal routing graph and unit tests.
- AGT-1.1 security remediation: immutable trusted context, internal graph-input boundary, metadata-free routing input and credential sanitization.
- AGT-1.1 final security fixes: controlled graph-input construction, server-owned message identifiers and provider-error exception isolation.
- AGT-1.2 implemented and verified: async injected specialist nodes, role-only prompts, sanitized generation requests, safe failures and Supervisor-to-specialist-to-END integration.
- AGT-1.2 review hardening: JSON-delimited role metadata, explicit specialist state validation and strict specialist mapping validation.
- AGT-1.2 invocation contract: legacy graphs retain sync invocation; specialist-enabled graphs reject sync calls with a clear async-only error; async invocation remains available.
- ORCH-P1 implementation branch: `feature/orch-p1-request-analyzer`. The separate local branch `feature/AGT-2.1-rag-mcp-tool-wiring` contains the AGT-2.1 capability-dispatch foundation.
- Proposed ORCH-P1 — Request Analyzer completed separately from the official AGT deliverables:
  - P1.1 — Added the strict `RequestAnalysis` domain contract.
  - P1.2 — Added the provider-independent analyzer input and asynchronous port.
  - P1.3 — Added the application analyzer boundary with message sanitization and bounded conversation context.
  - P1.4 — Integrated analysis into LangGraph with private workflow state, Quick/Context routing, terminal Deep handling, and safe analyzer failure propagation.
  - Security corrections — Added common credential-assignment redaction, Human/AI-only prior-context filtering, and a bounded routing-message role length.
  - Verification — Full test suite: 153 passed; focused tests for the latest corrections: 84 passed; Ruff passed.
- Proposed ORCH-P2 — Deep Planner completed separately from the official AGT deliverables:
  - P2.1 — Added strict, immutable planning domain contracts.
  - P2.2 — Added provider-independent planning input and asynchronous Planner port.
  - P2.3 — Enabled reuse of the exact sanitized, bounded analyzer input.
  - P2.4 — Added deterministic task ID, dependency, cycle and depth validation.
  - P2.5 — Added the application PlanningService with safe disposition and failure handling.
  - P2.6 — Integrated planning into the graph and standardized public outcomes through `WorkflowResult`.
  - Scope — Deep requests return a validated plan, clarification outcome or safe unsupported outcome. Tasks are not executed; no scheduler, MCP/RAG adapter or external integration was added.
  - Verification — Complete test suite: 261 passed; Ruff lint and formatting checks on the changed Python files passed.
- Approved architecture reconciliation on the ORCH-P2 branch adds the Conversational route, requires all three specialist nodes, bounds specialist session history, and defines the shared RAG retrieval boundary. Deep remains plan-only; no memory stores, RAG adapter, MCP integration or capability execution were added.
- Task 2.1 — Added environment-backed PostgreSQL settings, an async engine/session lifecycle, and an isolated Alembic environment for the Agent schema. The original database-name assumption was `support_ai_db`; it is superseded by the approved separate database `orchestrator_db`. Added configuration, engine/session, and migration-policy tests. At Task 2.1 completion no database adapter or migration revision was included; the following Task 2.2 added those.
- Task 2.2 — Added the SQLAlchemy Core acceptance tables, the `orchestrator` migration revision, and a PostgreSQL implementation of `AtomicRequestAcceptor` with scoped uniqueness and conflict-safe insertion. Historical verification skipped integration tests before a live test URL was configured. The migration is now applied at `20261126_01`; see the closeout record below for current verification.
- Task 2.2 review correction — Request acceptance now acquires a PostgreSQL transaction-scoped advisory lock for the trusted `(org_id, user_id, conversation_id)` scope, resolves idempotency before checking active executions, and returns `conversation_busy` for a new request when the conversation is active. The existing global message identity is not a per-conversation chronological sequence; per-conversation ordering is deferred to the Session Memory phase. PostgreSQL concurrency behavior requires the integration suite and is not established by unit tests.
- Shared PostgreSQL test target — The Agent uses the existing PostgreSQL server but connects only to the separate `orchestrator_db.orchestrator`; no separate Agent PostgreSQL container is configured. Host applications use `localhost:5433`, mapped to container port `5432`. Integration tests load `TEST_DATABASE_URL` from the root `.env` and remain skipped when it is absent.
- Closeout — Fixed Alembic's read-only preflight transaction boundary: validation queries are rolled back before Alembic configures its migration transaction. This prevents DDL and the version record from being rolled back when the connection closes. Unit regression tests cover both valid and invalid preflight cleanup, and the PostgreSQL integration suite asserts the recorded revision.
- Closeout verification — Applied `20261126_01`; read-only checks confirmed the three acceptance tables and `orchestrator.alembic_version` exist in `orchestrator`, the recorded revision is correct, the schema owner is `orchestrator_user`, and no acceptance/Alembic tables exist in `public`. `support_ai_db` was not connected to or queried. The focused PostgreSQL suite passed 18 tests; the full suite passed 349 tests. Ruff checks and formatting passed for Orchestrator source, tests, and migrations. `uv lock --check` passed.
- Local environment — Runtime and migration settings load the ignored root `.env` through Pydantic Settings. Pytest loads it before integration modules inspect `os.environ`, without overriding exported shell variables. The file is mode `600`; templates contain placeholders only.

Historical test counts differ across progress snapshots and completion summaries. Preserve the detailed completion evidence in the relevant task/review history; do not treat the counts below as a fresh test run.

## Official deliverables

| ID | Deliverable | Status |
|---|---|---|
| AGT-1.1 | LangGraph State & Supervisor Node | Complete |
| AGT-1.2 | Specialized Sub-Agent Nodes | Complete |
| AGT-2.1 | RAG & MCP Tool Wiring | Not started |
| AGT-3.1 | Human-in-the-Loop (HITL) Refund Gate | Not started |
| AGT-3.2 | Graceful RBAC Refusal Handling | Not started |
| AGT-4.1 | Adversarial Red-Teaming Suite | Not started |
| AGT-4.2 | Interactive Demo UI | Not started |

## Proposed orchestration workstream

These are temporary planning labels, not official AGT task IDs. Team ownership/IDs have not been assigned.

| Proposed work | Scope | Status |
|---|---|---|
| ORCH-P1 | Request Analyzer and Conversational/Quick/Context/Deep routing | Complete |
| ORCH-P2 | Deep Planner and plan/DAG validation | Complete |
| ORCH-P3 | Execution state, scheduler and specialist task interface | Not started |
| ORCH-P4 | Aggregation, partial failures and reliability | Not started |

## Not yet confirmed / not done

- Live integration with Backend, MCP or RAG.
- AGT-2.1 adapters and capability registration.
- Task execution, scheduler and Aggregator implementation (ORCH-P3/P4).
- Formal team assignment/IDs for ORCH-P1–P4.
- Analyzer quality evaluation against the approved four-mode classification rules.
- Final RAG authentication/context propagation details with RAG owner.
- Final MCP transport/session lifecycle details with MCP owner.
- Final execution checkpoint retention/access policy.
- Cross-organization shared-knowledge behavior.
- Account-memory ownership and storage.
- Memory/checkpoint retention, deletion, access and audit policy.
- Exact checkpoint contents and sensitive-data boundaries.
- Durable worker lease, claim and restart-recovery semantics.
- Dockerfiles/Compose and deployment setup (verify current workspace before changing status).

Do not mark work complete unless actually implemented and verified.

## Immediate next steps

1. Confirm remaining team-owned decisions: capability allowlists, RAG context propagation, MCP transport/error behavior, formal ORCH task ownership and classification rubric.
2. Finalize AGT-2.1 implementation design and dependencies.
3. Implement AGT-2.1 capability contracts/adapters using only defined operations; do not expand it into the complete persistence or memory system.
4. Establish the approved PostgreSQL checkpointing and durable recovery foundation before AGT-3.1 depends on HITL interruption/resumption.
5. Continue planning ORCH-P3 and ORCH-P4 as separately approved workstreams; ORCH-P1 and ORCH-P2 are complete, and these proposed workstreams are not mandatory prerequisites for AGT-3.1.

## Update rule

For each completed deliverable/workstream record:
- implementation summary,
- changed files,
- tests actually run/results,
- integration blockers,
- unresolved decisions,
- suggested commit message.

The user commits and pushes manually.
