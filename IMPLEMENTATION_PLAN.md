# Support Agent Orchestrator — Implementation Plan

**Status:** Architecture direction approved by the project user; detailed implementation decisions remain subject to the approvals listed in this document.
**Python:** `>=3.12,<3.13`
**Repository:** `support-agent-orchestrator`

## 1. Purpose and scope

Build an independently deployed Agent Orchestrator service for a multi-tenant B2B customer-support application. It coordinates LangGraph workflows, integrates with Backend/MCP/RAG/LLM services, supports HITL workflows, and exposes HTTP/SSE interfaces to Backend.

The Agent service does not own business records such as customers, tickets, invoices, official ticket messages, staff notes or business audit logs. Those remain Backend-owned.

The seven official deliverables, IDs, descriptions and order are fixed by the shared project agreement and are reproduced unchanged in `DELIVERABLE_MAPPING.md`. The new workflow-orchestration architecture is an approved project direction, but it is not a newly assigned official AGT task. It must be tracked separately until the team assigns formal task ownership/IDs.

Full account-memory extraction/retrieval, summaries and compaction remain deferred until the official deliverables are complete unless formally reprioritized.

## 2. Authority and document ownership

- `docs/CONTRACTS.md` (Shared Team Contract v3.0) is authoritative and locked. Do not modify it independently.
- `INTEGRATION_CONTRACT.md` is the Agent-specific companion; it must not override the shared contract.
- `AGENTS.md` contains persistent implementation and safety instructions.
- `docs/ORCHESTRATION_DESIGN.md` contains detailed workflow orchestration contracts and proposed schemas.
- `DELIVERABLE_MAPPING.md` preserves official deliverables and separately tracks proposed orchestration work.
- `PROGRESS.md` records actual implementation status only.

If a capability, schema, permission or endpoint is absent from the shared contract, do not invent it. Raise the gap with the owning teammate.

## 3. System and deployment architecture

The application request path is:

```text
Frontend -> Backend API/Gateway -> Agent Orchestrator
                                  +-> Backend REST APIs
                                  +-> MCP server
                                  +-> RAG service
                                  +-> LLM provider
```

Frontend communicates through Backend. Backend forwards authenticated requests and proxies SSE without buffering.

Run API and workflow execution separately:
- API process: request validation, authentication integration, workflow submission, status and SSE endpoints.
- Worker process: claims durable jobs and executes LangGraph workflows.
- PostgreSQL: jobs, checkpoints and Agent-owned operational persistence.

Start with PostgreSQL-backed job dispatch. Do not add Redis or another broker without a demonstrated need and approved design. API/worker coordination must not depend on process-local booleans or in-memory queues.

## 4. Architecture principles and workflow topology

Use Hexagonal Architecture (Ports and Adapters):
- Core orchestration is independent of infrastructure.
- Ports are separate from adapter implementations.
- Dependency injection and explicit registration select adapters/capabilities.
- FastAPI and SSE remain outside the graph core.
- The graph is independently invokable/testable.
- Use mocks while external services are unavailable.
- Avoid premature abstraction.

### 4.1 Components and responsibilities

1. **Request Analyzer:** receives sanitized current request and bounded relevant conversation context; classifies `conversational`, `quick`, `context` or `deep` and describes intent/requested outcomes. It does not authorize, choose tenant filters, grant capabilities or execute tools.
2. **Conversational response path:** gives lightweight replies to greetings, acknowledgements, closings and general assistant-capability questions without invoking Supervisor or a specialist.
3. **Supervisor:** routes Quick/Context requests to exactly one specialist (Triage, Knowledge or Billing).
4. **Planner:** for Deep requests, produces a bounded structured task plan. Planner output is untrusted and cannot grant access or expand the capability set.
5. **Plan Validator:** deterministic application code validates the structural planning contract. The completed ORCH-P2 validator checks task IDs, specialist assignments, dependencies, cycles and task/depth bounds. Capability and argument validation belongs to a later execution design; ORCH-P2 planned tasks do not contain capability names or arguments.
6. **Workflow Orchestrator / Scheduler:** centrally schedules ready tasks, enforces dependencies/concurrency/deadlines, dispatches specialists, collects outcomes and determines blocked/terminal tasks.
7. **Specialists:** execute a task-scoped objective with sanitized context, dependency summaries and an explicit capability allowlist. They cannot call other specialists or mutate the plan.
8. **Result Aggregator:** combines validated outcomes/evidence, preserves attribution and uncertainty, and identifies missing/failed sources before the final response.

### 4.2 Conversational, Quick and Context flow

Conversational messages follow Analyzer → lightweight response → END, without Supervisor or specialist invocation. Conversational includes greetings, acknowledgements, closings and general assistant-capability questions with no customer-specific support outcome.

```text
START
  -> authenticate/resolve trusted context at API-worker boundary
  -> sanitize and validate graph input
  -> Request Analyzer
  -> Supervisor
  -> exactly one specialist
  -> response
  -> END
```

Quick means one self-contained support outcome. It may require company-knowledge retrieval through RAG but does not materially depend on prior conversation or account-specific information.

Context means one support outcome that materially depends on relevant previous conversation or customer-specific context. It does not imply unrestricted history injection or multi-specialist execution.

The current specialist session-history policy includes the current HumanMessage once and at most the latest 10 earlier Human/AI messages in chronological order. System and Tool messages are excluded. The current request is limited to 4,000 characters, prior messages to 2,000 characters each, and prior context to 10,000 characters total. Selected content is sanitized before generation. This is bounded session history, not a memory store.

The typed four-mode analyzer contract and graph integration are implemented in proposed ORCH-P1. Classification quality should be evaluated against representative and ambiguous examples. Malformed output and provider failures propagate safely without fallback classification; no invalid analysis reaches Supervisor, Planner or a specialist.

### 4.3 Deep flow

```text
START
  -> authenticate/resolve trusted context at API-worker boundary
  -> sanitize and validate graph input
  -> Request Analyzer
  -> Planner
  -> deterministic Plan Validator
  -> Workflow Orchestrator
       -> dispatch ready specialist tasks
       -> wait/collect task outcomes
       -> update task lifecycle
       -> repeat while runnable tasks remain
  -> Result Aggregator
  -> final response
  -> END
```

The orchestrator is the only component that schedules tasks. It runs independent ready tasks concurrently within a configured bound. A task becomes ready only when all dependencies have succeeded. Failed prerequisites block dependent tasks; unrelated tasks may continue when safe. The workflow terminates when every task is terminal or a workflow bound is reached.

**Current implementation status:** ORCH-P2 currently ends after producing a validated plan (or a clarification/unsupported outcome). It does not execute or schedule tasks, invoke specialists for Deep requests, or aggregate task results. These are proposed ORCH-P3/P4 responsibilities. AGT-2.1 MCP/RAG adapters and external integrations remain not started and are tracked separately.

Use one central LangGraph with ordinary nodes and explicit conditional transitions initially. Do not add individual specialist subgraphs unless separately approved.

## 5. Conversation and execution state

The existing four-field `AgentState` remains the conversation-state baseline:
- `messages`
- `user_context`
- `active_agent`
- `approval_status`

Do not conflate conversation history with one Deep execution's task lifecycle. Define a separate typed execution-state schema or isolated execution envelope for analysis, validated plan, task statuses/results, execution bounds and final aggregation.

See `docs/ORCHESTRATION_DESIGN.md` for illustrative schemas and interface boundaries. Those schemas are design proposals, not shared-contract amendments.

Do not persist raw JWTs, bearer tokens, credentials, secrets, unbounded MCP/RAG payloads or unnecessary PII. Persist only bounded summaries/evidence references needed for execution and any approved resume behavior. Define retention/access controls before production checkpointing of customer data.

Keep `user_id`, `conversation_id` and LangGraph `thread_id` distinct. Initially one persistent thread maps to one conversation. Allow only one active execution per conversation, enforced durably across API and worker processes.

### 5.1 Memory and persistence tiers

The architecture preserves three conceptually separate tiers:

1. **Company memory:** organization policies, procedures, product information and company knowledge retrieved through the external RAG service. RAG enforces trusted `org_id` and `authorized_kb_tiers`; cross-organization shared knowledge is not defined by the current contract.
2. **Account memory:** persistent customer information scoped by `(org_id, user_id)`. It is not authoritative for identity, authorization or current business data. Full extraction, retrieval, summarization and compaction are deferred until the official deliverables are complete unless formally reprioritized; ownership and storage remain unresolved.
3. **Session memory:** conversation history, summaries and ongoing issue context scoped by conversation/thread. It is distinct from LangGraph checkpoints.

Context Assembly combines relevant information from these sources but does not own their underlying storage. Memory stores and their retrieval lifecycles remain unimplemented.

Conversation state, per-run execution state, PostgreSQL checkpoints and long-term account memory are distinct. No memory tier may establish identity, authorization, tenant scope or permissions; authenticated trusted context and Backend/MCP/RAG authorization remain authoritative.

## 6. Capability layer and currently available tools

The orchestration engine must be tool-transport independent. Specialists consume typed capability interfaces; adapters handle MCP/RAG protocol details, connection lifecycle, authentication forwarding, input/output validation and shared error mapping.

Currently defined capabilities are exactly:

**RAG**
- RAG is a separate external service, not an MCP tool. The provider-independent `KnowledgeRetriever` port uses `retrieve_kb(query, limit=5)` and the exact result fields in `docs/CONTRACTS.md`.
- One application retrieval boundary derives trusted organization and authorized-tier scope from authenticated runtime context and supplies it separately from the query. The RAG authority enforces both restrictions.
- Context Assembly and the Knowledge specialist will share this retrieval implementation. Context Assembly may retrieve initial relevant company knowledge; future on-demand retrieval for Knowledge is through an application-level capability. Triage and Billing may consume supplied passages but cannot independently retrieve them.
- The port and typed result contract are implemented. No external adapter, endpoint, transport or authentication behavior is assumed or implemented; those details require RAG-owner confirmation.

**MCP**
- `get_ticket_details`
- `search_tickets`
- `create_ticket`
- `update_ticket_status`
- `add_internal_note`
- `issue_refund`

Do not invent invoice/payment lookup, reconciliation, note-reading or other tools. The sample Deep scenario involving invoice/payment reconciliation is not executable with the current tool set. If a user request requires unavailable operations, report the limitation.

### 6.1 Proposed specialist capability allowlists

| Specialist | Default application-level allowlist |
|---|---|
| Triage | `get_ticket_details`, `search_tickets`, `create_ticket`, `update_ticket_status`, `add_internal_note` |
| Knowledge | `retrieve_kb` |
| Billing | `issue_refund` |

This is a proposed application-level exposure map, not an authorization policy. Backend/MCP remains authoritative. `add_internal_note` is staff-only under the shared contract. Do not expose discovered MCP tools automatically. Any later cross-specialist capability grant requires an explicit reviewed change.

### 6.2 Refund boundary

The shared contract defines `issue_refund` with an optional `approval_token` and requires LangGraph interruption plus explicit Org_Admin approval for amounts over `$100.00`. Backend owns approval token creation, validation, single-use consumption and business authorization.

AGT-2.1 may establish the adapter/schema/registration and safe error mapping, but must not bypass the approval contract. Until AGT-3.1 is implemented, do not invoke `issue_refund` for a request requiring the approval workflow. Return a safe outcome explaining that the approval workflow is not yet available. Do not fabricate tokens or approvals. AGT-3.1 owns interrupt, checkpoint, approval/rejection, resume and approved execution.

For amounts not requiring HITL, follow the exact shared contract and downstream authorization; do not infer additional permission rules.

## 7. Plan validation, scheduling and result aggregation

The completed ORCH-P2 plan validator rejects:
- Unknown specialist.
- Duplicate task IDs.
- Missing/unknown/self dependencies.
- Cyclic dependencies.
- Invalid task ID syntax and excessive task count/dependency depth.
- Planner-supplied extra fields, including identity, tenant, role, permission, approval, capability or argument fields.

Future execution work must define and validate any task-scoped capability policy and arguments before dispatch. That work does not expand ORCH-P2 or complete AGT-2.1.

Scheduling:
- Execute only tasks whose dependencies all succeeded.
- Bound parallel task count and total workflow duration.
- Use per-operation timeouts.
- Retry only bounded transient failures; do not blindly retry side-effecting operations.
- Mark dependent tasks blocked/incomplete after prerequisite failure.
- Continue independent work where safe.
- Use contract-supported idempotency for side effects.
- Ensure deterministic state merging and reject conflicting writes for a task.

Task results should be typed and bounded: status, concise summary, completeness, evidence references and safe error code. Aggregation must distinguish facts from inference, preserve source attribution, surface conflicts, and state what could not be checked. It must never present partial execution as complete.

Whether final aggregation is deterministic application code or a provider-backed generation call remains a design decision. If generated, the model sees only validated bounded task summaries/evidence and cannot alter task state, permissions or capability registration.

## 8. Authentication and security

`docs/CONTRACTS.md` is authoritative:
- Validate Backend-issued JWTs according to the contract.
- Resolve trusted context through the agreed `/auth/me` lifecycle.
- Do not trust client-supplied identity, tenant, role or permissions.
- Do not assume roles/org/permissions are JWT claims.
- Never put raw JWTs/secrets in prompts or graph state.
- Forward credentials only to downstream services that require them.
- Downstream services remain authoritative for authorization and sensitive operations.
- Prevent cross-tenant leakage through retrieval, task state, checkpoints, logs and event replay.

`InternalGraphInput` validation is an in-process boundary, not proof of authentication provenance. The API/worker boundary must authenticate and resolve context before constructing graph input.

RAG must receive trusted caller context and enforce `org_id` and `authorized_kb_tiers`. Model/planner output must never set these filters. Treat user text, retrieved documents and MCP outputs as untrusted content; bound and delimit them and prevent embedded instructions from changing workflow behavior.

## 9. Streaming, failures, retries and cancellation

SSE is the initial transport. Persist event history and support event IDs / `Last-Event-ID`; authorize replay. An SSE disconnect does not cancel execution.

Keep workflow lifecycle status separate from conversation lifecycle. Support explicit cancellation where possible, while acknowledging that completed external side effects cannot be reversed.

Separate transient, permission, validation, conflict and unexpected failures. Map the shared error envelope into safe outcomes. Do not retry 401/403 or other non-transient failures. Retry transient read operations with bounded backoff. Side-effect retries require contract-supported idempotency.

Configure per-tool and overall workflow deadlines. HITL waiting does not consume normal active-execution time.

## 10. Database and persistence ownership

- Backend PostgreSQL database: `support_ai_db` (Backend-owned; Agent must not connect to it)
- Agent PostgreSQL database: `orchestrator_db`
- Backend-owned schema: `public`
- Agent-owned schema: `orchestrator`

The PostgreSQL server hosts separate Backend and Agent databases. The Agent database owner provisions `orchestrator_db.orchestrator`; Agent manages its own migrations/checkpoint setup there. Never modify Backend-owned tables/migrations. Never connect to `support_ai_db` or query Backend business tables directly.

**Current local persistence status:** The initial Agent migration `20261126_01` is applied to `orchestrator_db.orchestrator`. It creates `session_messages`, `executions`, and `idempotency_records`; it does not create job, checkpoint, SSE, or memory tables. The migration target is validated online, and the Alembic version table is stored in `orchestrator`. Local runtime, migration, and optional integration-test URLs are loaded from the ignored root `.env`; exported shell variables take precedence. Current verified host mapping is `localhost:5433` to container port `5432`.

Use `langgraph-checkpoint-postgres` for durable checkpointing. Verify the installed package API before configuring schema/search_path. Apply connection schema settings reliably to pooled connections. Keep application and checkpointer connection configuration explicit.

Agent-owned data may include jobs, checkpoints, conversation/ephemeral turn records and persisted SSE events. Memory implementation remains deferred.

PostgreSQL-backed LangGraph checkpointing and durable job recovery are foundational requirements before AGT-3.1 depends on HITL interruption and resumption. This foundation is separate from the complete memory system and does not expand AGT-2.1. Before implementation, define checkpoint contents/sensitive-data boundaries, retention/deletion/access/audit policy, and durable worker lease, claim and restart-recovery semantics.

## 11. Dependencies

- `langchain-mcp-adapters` is required by the official AGT-2.1 mapping. Verify version/API compatibility before implementation.
- A direct HTTP client dependency for RAG (for example `httpx`) may be needed if the adapter uses HTTP. Confirm existing dependencies and explain the direct dependency before adding it.
- No additional workflow engine is proposed; use existing LangGraph and Pydantic.
- Do not assume a specific LLM supports structured output or tool calling. A deterministic plan validator is mandatory regardless of how plans are proposed.

## 12. Official and proposed work breakdown

Official AGT tasks remain unchanged and in their existing order:
1. AGT-1.1 — LangGraph State & Supervisor Node (completed)
2. AGT-1.2 — Specialized Sub-Agent Nodes (completed)
3. AGT-2.1 — RAG & MCP Tool Wiring (not started)
4. AGT-3.1 — Human-in-the-Loop (HITL) Refund Gate
5. AGT-3.2 — Graceful RBAC Refusal Handling
6. AGT-4.1 — Adversarial Red-Teaming Suite
7. AGT-4.2 — Interactive Demo UI

Separately proposed orchestration work (IDs below are placeholders, not official AGT IDs):
- **ORCH-P1 — Request Analysis and Mode Routing (complete):** typed four-mode analysis, sanitized bounded analyzer input, Conversational response routing, and Quick/Context routing while preserving the one-specialist path with bounded session history.
- **ORCH-P2 — Deep Planning and Plan Validation (complete, P2.1–P2.6):** strict task/planning contracts, provider-independent Planner port, analyzer-input reuse, deterministic task/dependency DAG validation, application PlanningService and plan-only graph integration. Planned tasks contain IDs, specialist assignments, objectives, expected outputs and dependencies; no capability names or arguments. Bounds include 10 tasks, dependency depth 5, 10 expected outputs per task, 500-character objectives and 300-character expected outputs. Deep tasks are not executed.
- **ORCH-P3 — Workflow Execution and Specialist Task Contract:** execution state, scheduler, bounded concurrency, specialist task interface and task result collection.
- **ORCH-P4 — Aggregation and Reliability:** aggregation, partial results, timeouts, failure semantics, checkpoint/persistence policy and end-to-end regression.

ORCH-P1/P2 are proposed workstreams, separate from the official AGT deliverables. Their completion does not change official AGT statuses. In particular, AGT-2.1 external MCP/RAG adapter integration remains not started.

Recommended sequencing:
1. Complete/review AGT-2.1 capability contracts and adapters, with refund invocation safely gated pending AGT-3.1.
2. Establish the approved durable persistence foundation before AGT-3.1 relies on HITL interruption/resumption.
3. Continue official AGT-3.1/3.2/4.1/4.2 in their agreed order.
4. Continue ORCH-P3/P4 only as separately approved, tracked workstreams; completed ORCH-P1/P2 and future ORCH work are not mandatory prerequisites for AGT-3.1.

The team may choose to interleave the ORCH work with AGT-2.1, but that scheduling choice does not change official AGT definitions. Do not mark any proposed work complete until implemented and verified.

## 13. Deferred decisions and approval gates

Resolve before the relevant implementation:
- Evaluate Analyzer quality against the approved Conversational/Quick/Context/Deep rules; failures propagate without fallback classification.
- Final tool-to-specialist allowlists and any cross-specialist access.
- RAG authentication/context propagation and enforcement verification with RAG owner.
- MCP transport/session lifecycle and exact error propagation with MCP owner.
- Refund behavior before AGT-3.1; never bypass contract approval.
- Planner method (deterministic templates vs model-proposed plan) and structured-output capability.
- Aggregation method (deterministic vs generation).
- Execution concurrency, per-call and overall timeout values. ORCH-P2 plan bounds are set at 10 tasks and dependency depth 5; execution-specific limits remain to be defined.
- Cross-organization shared-knowledge behavior; the current RAG contract defines organization-scoped retrieval only.
- Tier 2 account-memory ownership and storage.
- Memory and checkpoint retention, deletion, access and audit policies.
- Exact checkpoint contents and sensitive-data boundaries.
- Durable worker lease, claim and restart-recovery semantics.
- Formal team task IDs/ownership for ORCH-P1–P4.

Do not invent invoice/payment lookup or reconciliation operations. Raise a contract gap with the relevant owner if a future use case requires them.

## 14. Testing

Test every adapter against contract schemas and shared error envelopes. Test capability registration/allowlists, unknown capability rejection, tenant-context propagation, no direct SQL, and no model-supplied tenant filters.

Test analyzer modes/fallback, planner invalid output, DAG validation, parallel independent tasks, dependency ordering, concurrency limits, task failures, blocked dependents, partial aggregation, timeouts, cancellation, safe checkpoint contents and existing AGT-1.1/1.2 regressions.

Mock Backend, MCP, RAG, LLM and persistence in unit tests. Run integration tests only where services are available. Never claim unexecuted tests passed.

## 15. Git and Codex workflow

The user exclusively controls commits and pushes. Codex must not commit, push, merge, rebase, amend, reset or rewrite history. Branch creation/switching requires explicit instruction.

Work in coherent feature-sized batches. Report changed files, tests actually run/results, unresolved issues and a suggested commit message. Explain dependencies before adding them and obtain approval for security-sensitive changes.
