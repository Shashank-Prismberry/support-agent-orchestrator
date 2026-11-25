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

## Proposed workflow-orchestration workstream (not official AGT tasks)

**Status:** Architectural direction approved by project user; implementation not started. The labels below are temporary planning identifiers only. They must not be represented as official AGT IDs or team-assigned tasks until formally approved.

### ORCH-P1 — Request Analysis and Mode Routing

Scope:
- Define and test Quick/Context/Deep classification rubric.
- Implement typed Request Analyzer over sanitized input/bounded relevant context.
- Preserve Quick/Context Supervisor → exactly one specialist route.
- Define conservative fallback for ambiguous/invalid analyzer output.

Acceptance:
- Analyzer cannot authorize, choose tenant filters or execute capabilities.
- Quick/Context invoke exactly one specialist.
- Existing AGT-1.1/1.2 behavior remains covered by regression tests.

### ORCH-P2 — Deep Planning and Plan Validation

Scope:
- Define typed task, dependency and result contracts.
- Add bounded Planner interface/implementation.
- Validate task IDs, specialist names, capability allowlists, arguments, dependencies, cycles, task count and depth.

Acceptance:
- Invalid or unsupported plans are rejected before execution.
- Planner cannot grant capabilities or set trusted identity/tenant/permission fields.
- Plans cannot reference capabilities beyond the six MCP tools and `retrieve_kb`.

### ORCH-P3 — Workflow Execution and Specialist Task Contract

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