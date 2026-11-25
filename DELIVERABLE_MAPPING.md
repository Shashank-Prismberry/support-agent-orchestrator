# Official Deliverable Mapping --- Support Agent Orchestrator

Preserve the official IDs, titles and order.

## AGT-1.1 --- LangGraph State & Supervisor Node

**Status:** Completed 2026-11-24.

**Official description:** Define `AgentState` (`messages`,
`user_context`, `active_agent`, `approval_status`) and implement
Supervisor intent router.

Implementation: typed state; message reducers; trusted user-context
contract; Supervisor node; intent routing; central graph construction
and transitions.

Tests: state creation/update; representative routing; unknown/ambiguous
intent; missing/invalid context; raw credentials absent from state;
deterministic mocked LLM routing.

Completion record: implemented a validated `TrustedUserContext`, typed
`AgentState`, provider-independent Supervisor routing port, and central
terminal routing graph. Tests cover all required routes, fallback and
failure paths, trusted-context validation, message reduction, graph
termination and sensitive-context boundaries. The suite passed with
100% coverage.

## AGT-1.2 --- Specialized Sub-Agent Nodes

**Status:** Completed 2026-11-24.

**Official description:** Implement Triage_Agent, Knowledge_Agent and
Billing_Agent nodes with role-aware system instructions.

Implementation: individual specialist nodes; role-aware instruction
construction from trusted context; common result/state conventions;
injected ports; central graph routing.

Tests: each agent independently; expected state updates; missing
context; agent/provider failures; role-aware instructions; specialists
cannot freely invoke each other; no raw JWT/secrets in prompts.

Completion record: implemented independently injected asynchronous
Triage, Knowledge, and Billing nodes with role-only prompt framing,
sanitized generation requests, safe output/provider failure handling,
and Supervisor-to-one-specialist-to-END graph integration. No external
tools, retrieval, authorization, or approval behavior was added.

## AGT-2.1 --- RAG & MCP Tool Wiring

**Official description:** Connect Knowledge_Agent to `retrieve_kb` and
connect Triage_Agent and Billing_Agent to MCP using
`langchain-mcp-adapters`.

Implementation: RAG port/HTTP adapter; MCP adapter; config/dependency
wiring; tool result/error mapping per shared contract.

Contract references: `retrieve_kb(query, limit=5)`; MCP tools include
`get_ticket_details`, `search_tickets`, `create_ticket`,
`update_ticket_status`, `add_internal_note`, `issue_refund`.

Tests: mocked adapter contract tests; discovery/invocation; invalid
inputs; timeouts/rate limits/unavailability; error mapping; no direct
SQL to Backend/RAG tables; no model-supplied tenant identity.

## AGT-3.1 --- Human-in-the-Loop (HITL) Refund Gate

**Official description:** Add LangGraph interrupt/checkpoint behavior on
`issue_refund` over \$100 requiring explicit Org_Admin approval.

Implementation: detect threshold; interrupt before protected action;
persist checkpoint; capture approval/rejection; resume same workflow;
use Backend's agreed approval mechanism. Agent must not fabricate
approval tokens or bypass Backend.

Tests: threshold behavior; no action before approval; authorized
approval resumes once; rejection blocks;
invalid/expired/replayed/mismatched approval rejected by owning service;
idempotency; unauthorized approver refused.

## AGT-3.2 --- Graceful RBAC Refusal Handling

**Official description:** Configure prompts/error handlers so 403
PermissionDenied yields polite refusal without exposing internal schema
or data.

Implementation: typed permission error; centralized error mapping; safe
user-facing messages; agent instructions; safe logging.

Tests: 403 refusal; no retry of permission denial; no hidden
schema/notes/data disclosure; distinct handling of 401 and other
contract errors; no alternate unauthorized path; no false success claim.

## AGT-4.1 --- Adversarial Red-Teaming Suite

**Official description:** Test prompt-injection and privilege-escalation
attacks across `alice_admin`, `bob_support` and `charlie_cust`.

Implementation: reusable adversarial cases; malicious user/retrieved
content; role escalation; cross-tenant attempts; tool misuse; approval
bypass; regression suite.

Tests: exact identities/scopes from `docs/CONTRACTS.md`; Org A/Org B
isolation; verify downstream authorization, not only prompts; no
unauthorized data in messages, events, logs or state.

## AGT-4.2 --- Interactive Demo UI

**Official description:** Build Streamlit or Chainlit chat app with
user/role switcher and HITL approval controls.

Implementation: choose UI framework when this deliverable begins;
approved test personas; chat; streaming; workflow progress; HITL
controls; safe errors/refusals.

Checks: persona switch uses approved identity flow; streaming displays
correctly; approval controls only for pending approvals; UI does not
bypass Backend auth.

## Cross-cutting requirements

-   Tests for normal, edge, invalid and failure cases.
-   Mock Backend/MCP/RAG/LLM in unit tests.
-   Authorization and tenant-isolation tests where relevant.
-   No secrets in source, prompts, logs or graph state.
-   No direct SQL to Backend business tables.
-   User reviews and commits.

Full account-memory extraction/retrieval, summaries and compaction are
deferred until official deliverables are complete; do not insert them as
blockers into AGT-1.1--AGT-4.2.
