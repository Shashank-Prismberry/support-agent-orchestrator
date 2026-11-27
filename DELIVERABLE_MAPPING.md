# Deliverable Mapping — Support Agent Orchestrator

Official task IDs, titles, descriptions and order are preserved. Proposed workflow-orchestration work is listed separately and is not represented as an official AGT assignment.

## Official deliverables

### AGT-1.1 — LangGraph State & Supervisor Node

**Status:** Completed 2026-11-24.

**Official description:** Define `AgentState` (`messages`, `user_context`, `active_agent`, `approval_status`) and implement Supervisor intent router.

Implementation: typed state; message reducers; trusted user-context contract; Supervisor node; intent routing; central graph construction and transitions.

Tests: state creation/update; representative routing; unknown/ambiguous intent; missing/invalid context; raw credentials absent from state; deterministic mocked LLM routing.

Completion record: implemented a validated `TrustedUserContext`, typed `AgentState`, provider-independent Supervisor routing port, and central terminal routing graph. Tests cover required routes, fallback/failure paths, trusted-context validation, message reduction, graph termination and sensitive-context boundaries. Historical completion record reports 100% coverage.

### AGT-1.2 — Specialized Sub-Agent Nodes

**Status:** Completed 2026-11-24.

**Official description:** Implement Triage_Agent, Knowledge_Agent and Billing_Agent nodes with role-aware system instructions.

Implementation: individual specialist nodes; role-aware instruction construction from trusted context; common result/state conventions; injected ports; central graph routing.

Tests: each agent independently; expected state updates; missing context; agent/provider failures; role-aware instructions; specialists cannot freely invoke each other; no raw JWT/secrets in prompts.

Completion record: implemented independently injected asynchronous Triage, Knowledge and Billing nodes with role-only prompt framing, sanitized generation requests, safe output/provider failure handling, and Supervisor-to-one-specialist-to-END graph integration. No external tools, retrieval, authorization or approval behavior was added.

### AGT-2.1 — RAG & MCP Tool Wiring

**Status:** Not started.

**Official description:** Connect Knowledge_Agent to `retrieve_kb` and connect Triage_Agent and Billing_Agent to MCP using `langchain-mcp-adapters`.

Implementation:
- RAG port/HTTP adapter for `retrieve_kb(query, limit=5)`.
- MCP adapter using exactly the six canonical tools: `get_ticket_details`, `search_tickets`, `create_ticket`, `update_ticket_status`, `add_internal_note`, `issue_refund`.
- Configuration/dependency wiring, explicit capability registration and safe result/error mapping per shared contract.
- Proposed application-level specialist allowlists are documented in `docs/ORCHESTRATION_DESIGN.md`; Backend/MCP authorization remains authoritative.
- Do not invent additional tools or query Backend/RAG tables directly.
- Do not bypass the shared `issue_refund` approval workflow. AGT-3.1 owns HITL execution. Until AGT-3.1 exists, do not invoke refunds that require its approval.

Tests: mocked adapter contract tests; discovery/invocation; invalid inputs; timeouts/rate limits/unavailability; shared error mapping; explicit registration/allowlists; no direct SQL; no model-supplied tenant identity or KB filters.

Architecture note: the provider-independent KnowledgeRetriever port and result contract are available as an architecture boundary, but no external RAG adapter or MCP integration is implemented. The official AGT-2.1 status remains Not started.

### AGT-3.1 — Human-in-the-Loop (HITL) Refund Gate

**Status:** Not started.

**Official description:** Add LangGraph interrupt/checkpoint behavior on `issue_refund` over `$100` requiring explicit Org_Admin approval.

Implementation: detect threshold; interrupt before protected action; persist checkpoint; capture approval/rejection; resume same workflow; use Backend's agreed approval mechanism. Agent must not fabricate approval tokens or bypass Backend.

Tests: threshold behavior; no action before approval; authorized approval resumes once; rejection blocks; invalid/expired/replayed/mismatched approval rejected by owning service; idempotency; unauthorized approver refused.

### AGT-3.2 — Graceful RBAC Refusal Handling

**Status:** Not started.

**Official description:** Configure prompts/error handlers so 403 PermissionDenied yields polite refusal without exposing internal schema or data.

Implementation: typed permission error; centralized error mapping; safe user-facing messages; agent instructions; safe logging.

Tests: 403 refusal; no retry of permission denial; no hidden schema/notes/data disclosure; distinct handling of 401 and other contract errors; no alternate unauthorized path; no false success claim.

### AGT-4.1 — Adversarial Red-Teaming Suite

**Status:** Not started.

**Official description:** Test prompt-injection and privilege-escalation attacks across `alice_admin`, `bob_support` and `charlie_cust`.

Implementation: reusable adversarial cases; malicious user/retrieved content; role escalation; cross-tenant attempts; tool misuse; approval bypass; regression suite.

Tests: exact identities/scopes from `docs/CONTRACTS.md`; Org A/Org B isolation; verify downstream authorization, not only prompts; no unauthorized data in messages, events, logs or state.

### AGT-4.2 — Interactive Demo UI

**Status:** Not started.

**Official description:** Build Streamlit or Chainlit chat app with user/role switcher and HITL approval controls.

Implementation: choose UI framework when this deliverable begins; approved test personas; chat; streaming; workflow progress; HITL controls; safe errors/refusals.

Checks: persona switch uses approved identity flow; streaming displays correctly; approval controls only for pending approvals; UI does not bypass Backend auth.

## Agent persistence foundation (separate engineering work; no official AGT ID)

**Status:** Initial acceptance persistence is implemented and locally integration-tested.

- SQLAlchemy 2.x async with `asyncpg`, Core tables, and an Agent-owned Alembic environment target only `orchestrator_db.orchestrator`.
- `AtomicRequestAcceptor` persists the inbound session message, accepted execution, scoped idempotency record, and dispatch eligibility in one transaction. A PostgreSQL advisory lock enforces one active execution per trusted conversation scope.
- Migration `20261126_01` is applied locally. It creates `session_messages`, `executions`, and `idempotency_records`; the Alembic version table is in `orchestrator`.
- Verification: 18 PostgreSQL acceptance integration tests and the full 349-test suite passed during closeout. These results establish local acceptance behavior, not an API, worker, checkpoint, SSE, or memory implementation.
- Deferred: durable job dispatch/claims, LangGraph checkpointing, conversation-history retrieval, Account Memory, Context Assembly, and the full memory lifecycle. These do not receive new official AGT IDs here.

## Proposed workflow-orchestration workstream (not official AGT tasks)

**Status:** Architectural direction approved by project user. ORCH-P1 and ORCH-P2 are implemented; ORCH-P3 and ORCH-P4 are not started. These are proposed workstreams, not official AGT deliverables or team-assigned tasks.

### ORCH-P1 — Request Analysis and Mode Routing

**Status:** Complete.

Scope:
- Implement and test the typed Conversational/Quick/Context/Deep analysis contract and graph routing for those mode values.
- Implement typed Request Analyzer over sanitized input/bounded relevant context.
- Route Conversational requests to a lightweight response path without Supervisor or specialist invocation.
- Preserve Quick/Context Supervisor → exactly one specialist route.
- Require all three specialist nodes and pass bounded, sanitized session history to specialist generation.
- Propagate malformed output and provider failures safely without silent fallback classification.

Acceptance:
- Analyzer cannot authorize, choose tenant filters or execute capabilities.
- Quick/Context invoke exactly one specialist.
- Conversational invokes no Supervisor or specialist.
- Specialist generation excludes System/Tool messages and applies explicit message and character bounds.
- Existing AGT-1.1/1.2 behavior remains covered by regression tests.
- Mode values are validated and routed without silent fallback classification.

Semantic classification quality evaluation remains deferred until a concrete Analyzer provider is available. The current implementation defines the classification contract and graph routing; it does not enforce message-to-mode semantics.

### ORCH-P2 — Deep Planning and Plan Validation

**Status:** Complete (P2.1–P2.6).

Scope:
- Define strict task and planning-result contracts. Each planned task contains an ID, specialist, objective, expected outputs and dependencies; it contains no capability names or capability arguments.
- Add the provider-independent asynchronous Planner port and application PlanningService.
- Reuse the exact sanitized and bounded request input prepared by the Request Analyzer.
- Validate task IDs, specialist names, dependencies, cycles, task count and dependency depth.
- Integrate plan-only Deep outcomes into the graph while preserving Quick/Context routing.

Acceptance:
- Invalid proposals and dependency graphs are rejected before a plan is returned.
- Planner cannot receive trusted identity/tenant/permission data or grant authorization.
- Deep requests currently return a validated plan, clarification outcome or fixed safe unsupported outcome; tasks are not executed or scheduled.
- ORCH-P2 does not implement or complete AGT-2.1 external MCP/RAG integration.

### ORCH-P3 — Workflow Execution and Specialist Task Contract

**Status:** Not started. Owns future task execution and scheduling.

Scope:
- Define separate per-run execution state.
- Add central DAG scheduler and task lifecycle.
- Dispatch specialist tasks through a provider/transport-independent interface.
- Support bounded parallel ready tasks, dependency handling, timeouts and safe partial failure.

Acceptance:
- Specialists cannot invoke one another or mutate the plan.
- Dependencies execute in order; independent tasks can run concurrently within limits.
- Failed prerequisites block dependents; unrelated work may continue safely.
- State merging is deterministic and checkpoint data is bounded.

### ORCH-P4 — Aggregation and Reliability

Scope:
- Add Aggregator over validated task outcomes/evidence.
- Preserve attribution, conflicts, uncertainty and incomplete sources.
- Finalize timeout, cancellation, retry and checkpoint/retention policies.
- Add end-to-end tests across all request modes.

Acceptance:
- Partial execution is never presented as complete.
- No unsupported capability result is invented.
- No credentials or untrusted authorization claims enter state/prompts/checkpoints.
- Regression tests preserve AGT-1.1/1.2 and adapter/security boundaries.

## Cross-cutting requirements

- Tests for normal, edge, invalid and failure cases.
- Mock Backend/MCP/RAG/LLM in unit tests.
- Authorization and tenant-isolation tests where relevant.
- No secrets in source, prompts, logs or graph state.
- No direct SQL to Backend business tables or RAG tables.
- User reviews and commits.
- Full account-memory extraction/retrieval, summaries and compaction remain deferred until official deliverables are complete.
