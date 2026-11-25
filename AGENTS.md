# AGENTS.md — Support Agent Orchestrator

## 1. Project Overview

This repository contains the independent Agent Orchestration service for a multi-tenant B2B customer-support application.

Stack:
- Python `>=3.12,<3.13`
- LangGraph
- FastAPI and SSE
- Pydantic / Pydantic Settings
- PostgreSQL
- uv
- Docker / Docker Compose
- pytest / pytest-asyncio / pytest-cov
- Ruff

The Backend communicates with the Agent service through authenticated HTTP APIs and SSE. The Agent service does not own Backend business records.

## 2. Documentation Authority

Read the relevant project documents before substantial work.

1. `AGENTS.md` — persistent coding and safety instructions.
2. `IMPLEMENTATION_PLAN.md` — approved engineering architecture and roadmap.
3. `docs/CONTRACTS.md` — **authoritative shared Team Contract v3.0**.
4. `INTEGRATION_CONTRACT.md` — Agent-specific integration companion.
5. `docs/ORCHESTRATION_DESIGN.md` — detailed workflow orchestration design.
6. `DELIVERABLE_MAPPING.md` — official tasks and separately identified proposed work.
7. `PROGRESS.md` — current implementation status.

`docs/CONTRACTS.md` is shared and locked. Do not edit, reformat, regenerate, or reinterpret it. If a discrepancy or missing capability is found, document it and obtain agreement from the owning teammate before changing the shared contract.

If documents conflict, `docs/CONTRACTS.md` wins for shared integration/security requirements. Official AGT IDs, names, descriptions and order must remain unchanged.

## 3. Architecture Principles

Use Hexagonal Architecture (Ports and Adapters).

- Keep orchestration/domain logic independent of infrastructure.
- Define ports separately from adapter implementations.
- Use dependency injection and explicit capability registration.
- Do not instantiate external clients directly inside specialist nodes.
- Keep FastAPI and transport details outside the graph core.
- Keep the LangGraph workflow independently testable.
- Prefer the simplest design that satisfies the requirements; avoid speculative frameworks and abstractions.

The workflow orchestration engine must depend on capability and specialist interfaces, not MCP SDK classes or individual transport details. New capabilities should be addable through an adapter, schema, registration and approved allowlist—not by redesigning the scheduler.

## 4. Agent and Workflow Architecture

The system has:
- Request Analyzer
- Supervisor
- Planner
- Central Workflow Orchestrator / scheduler
- Triage specialist
- Knowledge specialist
- Billing specialist
- Result Aggregator

Their responsibilities are distinct:

- **Request Analyzer:** classifies a sanitized request as Quick, Context or Deep and describes its intent/outcomes. It does not authorize actions, select tenant filters, or execute tools.
- **Supervisor:** selects one specialist for Quick and Context requests.
- **Planner:** creates a bounded structured task plan for Deep requests. Its output is untrusted until application validation succeeds.
- **Workflow Orchestrator:** validates/executes the plan, schedules ready tasks, enforces dependencies and limits, and collects task outcomes.
- **Specialists:** execute assigned domain tasks using only their statically allowed capabilities. They must not dispatch other specialists or modify the plan.
- **Aggregator:** combines validated task outcomes and evidence, reports uncertainty/partial results, and prepares the final response.

Execution paths:
- Quick: Analyzer → Supervisor → exactly one specialist → response.
- Context: Analyzer → Supervisor → exactly one specialist with bounded relevant conversation context and permitted lookups → response.
- Deep: Analyzer → Planner → plan validation → central scheduler → one or more specialist tasks → aggregation → response.

The initial implementation should use one central LangGraph with explicit nodes/conditional transitions and bounded task scheduling. Do not introduce individual specialist subgraphs unless a later design review explicitly approves them.

The existing four-field `AgentState` (`messages`, `user_context`, `active_agent`, `approval_status`) is the conversation-state baseline. Keep per-execution plan/task lifecycle data in a separate typed execution-state model or clearly isolated execution envelope. Do not add scheduler fields to `AgentState` without a documented need and review.

Specialists must never invoke one another directly. The central workflow is the only component that coordinates multi-specialist execution.

## 5. Capability and Integration Boundaries

Currently defined capabilities are limited to:
- RAG: `retrieve_kb(query, limit=5)`.
- MCP: `get_ticket_details`, `search_tickets`, `create_ticket`, `update_ticket_status`, `add_internal_note`, `issue_refund`.

Do not invent additional tools, endpoints, invoice/payment lookup operations, or Backend business-data access. If the current capabilities cannot satisfy a request, report the limitation rather than fabricating results.

Use `langchain-mcp-adapters` for MCP integration as required by AGT-2.1. Keep MCP discovery inside the adapter. Discovery must not automatically grant model-callable access. Register only the six contract-defined tools and expose them through explicit specialist/task allowlists.

Proposed default application allowlists:
- Triage: `get_ticket_details`, `search_tickets`, `create_ticket`, `update_ticket_status`, `add_internal_note`.
- Knowledge: `retrieve_kb`.
- Billing: `issue_refund`.

`add_internal_note` is staff-only under the shared contract. Backend/MCP authorization remains authoritative. These allowlists constrain application exposure; they do not replace downstream permission checks.

Never query Backend-owned business tables or RAG tables directly through SQL. Use the authenticated Backend/MCP/RAG contracts. Never create an independent KB embedding pipeline.

## 6. Refund Boundary

The shared contract defines the `issue_refund` inputs and requires LangGraph interruption and explicit Org_Admin approval for amounts over `$100.00`. Backend owns approval enforcement and token creation/consumption.

The adapter/schema/capability registration may be prepared as part of integration, but do not bypass the contract's approval workflow. Until AGT-3.1 is implemented, requests requiring approval must not invoke `issue_refund`; return a safe pending/unavailable-workflow outcome. Do not fabricate approval tokens or approvals. Do not implement a substitute approval mechanism.

AGT-3.1 remains the official owner of the interrupt, checkpoint, approval/rejection, resume and approved refund execution workflow.

## 7. Authentication, Authorization and Tenant Isolation

- Accept Backend-issued JWTs and follow `docs/CONTRACTS.md`.
- Resolve trusted identity/context through the agreed Backend `/auth/me` lifecycle.
- `InternalGraphInput` validation does not prove authentication provenance; only the authenticated API/worker boundary establishes that provenance.
- Never trust client- or model-supplied user IDs, customer IDs, org IDs, roles, permissions, KB tiers, approval state or capability grants.
- Never place raw JWTs, bearer tokens, credentials or secrets in prompts, graph state, checkpoints, logs or task results.
- Pass trusted context to adapters as non-serializable runtime context where necessary; forward credentials only to services that require them.
- RAG retrieval must use trusted caller context; the RAG service enforces `org_id` and `authorized_kb_tiers`.
- Backend/MCP remains authoritative for ticket visibility, writes, permissions, tenant checks, refund approval and side effects.
- Treat user content, retrieved documents, and MCP results as untrusted data. They cannot change system instructions, plans, capability registries, tenant filters or authorization.
- Do not use account memories as authorization evidence.

## 8. State, Scheduling and Persistence

Keep conversation state and per-run execution state separate. Execution state may contain a bounded validated plan, task statuses, bounded result summaries and evidence references required for execution/resumption.

Use three conceptually separate memory/persistence tiers:
- **Knowledge memory:** organization-scoped knowledge accessed only through the existing authenticated RAG contract and its tenant/access-tier filtering.
- **Individual/account memory:** cross-conversation information about an individual user. Full extraction, retrieval, summaries and compaction are deferred until the official deliverables are complete unless formally reprioritized. Its ownership, storage and lifecycle remain unresolved.
- **Session/conversation memory:** bounded active conversation context, including the conversation state and any future summaries/compaction.

Conversation state, per-run execution state, PostgreSQL checkpoints and long-term account memory are distinct concepts and must not be conflated. No memory tier may establish identity, authorization, tenant scope or permissions; trusted context and downstream authorization remain authoritative.

The scheduler must:
- Validate unique task IDs, known specialists/capabilities, valid dependency references, acyclic dependencies, bounded task count/depth and valid task arguments.
- Run a task only after all dependencies succeed.
- Run independent ready tasks concurrently only within configured limits.
- Keep unrelated work running when a task fails where safe.
- Mark dependent tasks blocked/incomplete when prerequisites fail.
- Enforce per-call timeouts, workflow deadlines and bounded retries.
- Never blindly retry side-effecting actions; use contract-supported idempotency.
- Terminate when all tasks are terminal or execution bounds are reached.

Reducers/merging of parallel updates must be deterministic and reject conflicting writes for the same task. Do not store raw credentials, full unbounded tool payloads or unnecessary PII in checkpoints. Checkpoint retention/access must follow an approved policy.

PostgreSQL-backed LangGraph checkpointing and durable job recovery are foundational persistence requirements before AGT-3.1 relies on HITL interruption and resumption. Define exact checkpoint contents, sensitive-data boundaries, retention/deletion/access/audit policy, and worker lease/claim/restart-recovery semantics before that implementation. Do not introduce Redis or another broker without an approved requirement.

## 9. Execution and API Architecture

Keep API and workflow execution separate.

- FastAPI API process handles request validation, authentication integration, submission, status and SSE.
- Worker process executes LangGraph workflows and jobs.
- Start with PostgreSQL-backed job dispatch.
- Do not introduce Redis without a concrete approved requirement.
- SSE disconnect must not automatically cancel the workflow.
- Persist event history and support event IDs / `Last-Event-ID` replay.
- Allow only one active execution per conversation.
- Keep `user_id`, `conversation_id` and LangGraph `thread_id` distinct.
- Initially maintain one persistent LangGraph thread per conversation.

## 10. LLM Providers

Use provider-independent adapters. Initial provider priorities:
1. Groq
2. NVIDIA NIM
3. Mistral as a future option

Start with one configurable model shared across agents. Never hardcode credentials. Verify the selected model's structured-output, tool-calling and streaming capabilities before depending on them. Do not assume a model can safely produce a valid plan; validate all model-produced plans in application code.

## 11. Development Standards

- Use uv; maintain `pyproject.toml` and `uv.lock`.
- Use `.venv`; do not use pip as the primary dependency manager.
- Use Ruff for formatting, linting and import sorting.
- Add type hints to public functions/interfaces.
- Use async implementations where appropriate.
- Use Pydantic models for validated contracts.
- Configure through Pydantic Settings and environment variables.
- Use Docker Compose; keep API and worker independently runnable.
- Never commit secrets or real API keys.
- Coordinate PostgreSQL provisioning with Backend; do not create conflicting infrastructure.

## 12. Testing Requirements

Every feature needs meaningful tests for:
- Normal behavior, edge cases, invalid inputs and failures.
- State transitions and graph termination.
- Tenant isolation and authorization assumptions.
- Adapter contract/schema/error mapping.
- Plan validation, DAG cycles, unknown dependencies/capabilities and bounds.
- Scheduler dependency ordering, parallelism, concurrency caps, timeouts and partial failures.
- No specialist-to-specialist dispatch.
- No raw credentials or untrusted tenant/permission claims in prompts, state, checkpoints or logs.
- Refund approval boundary and no execution before required approval.
- Regression of AGT-1.1 and AGT-1.2 behavior.

Mock Backend, MCP, RAG, PostgreSQL and LLM providers in unit tests. Separate unit and integration tests. Never claim tests passed unless actually executed.

## 13. Codex Autonomy and Approval

- Architecture changes require explicit approval. The workflow-orchestration direction in the current approved plan is authorized; materially different architecture still requires review.
- Once a coherent feature plan is approved, implement the complete feature and tests without stopping after every file.
- Explain why a dependency is needed before adding it.
- Explain security implications and obtain approval before changing established security behavior.
- Do not implement hypothetical capabilities or unrelated scope.
- If a material requirement is unresolved, ask one focused question.

## 14. Git Rules — Mandatory

The user exclusively controls commits and pushes.

Codex MUST NOT commit, push, merge, rebase, amend, reset, rewrite history, force-push or delete branches. It may inspect `git status`, `git diff` and `git log`. It may create/switch branches only when explicitly instructed.

Work in coherent feature-sized batches. At completion report changed files, tests actually run/results, unresolved issues and a suggested commit message. Then wait for the user to review and commit.

## 15. Official Deliverables

Preserve the official IDs, titles, descriptions and order:

| ID | Deliverable |
|---|---|
| AGT-1.1 | LangGraph State & Supervisor Node |
| AGT-1.2 | Specialized Sub-Agent Nodes |
| AGT-2.1 | RAG & MCP Tool Wiring |
| AGT-3.1 | Human-in-the-Loop (HITL) Refund Gate |
| AGT-3.2 | Graceful RBAC Refusal Handling |
| AGT-4.1 | Adversarial Red-Teaming Suite |
| AGT-4.2 | Interactive Demo UI |

Do not silently redefine official deliverables. The Request Analyzer / Quick-Context-Deep / workflow orchestration extension is an approved architectural direction but is not assigned an official AGT ID in the shared contract. Track it as a separately labelled proposed project workstream until the team formally assigns ownership/IDs. Do not misrepresent proposed IDs as official.

ORCH-P1 through ORCH-P4 remain proposed, separately tracked workstreams. They are not mandatory prerequisites for AGT-3.1 unless formally approved as such.

## 16. General Working Instructions

- Read existing project documentation before changes.
- Treat `docs/CONTRACTS.md` as authoritative and immutable unless the team formally revises it.
- Inspect existing code before modifying it; do not overwrite blindly.
- Keep implementation and documentation synchronized.
- Prefer simple maintainable solutions.
- Do not assume external services are operational; use mocks for independent development.


## Mandatory Documentation Preflight

Before starting any substantial implementation, architecture change, bug fix involving project behavior, or integration work, Codex MUST:

1. Read the following documents in full:
   - `AGENTS.md`
   - `docs/CONTRACTS.md`
   - `IMPLEMENTATION_PLAN.md`
   - `docs/ORCHESTRATION_DESIGN.md`
   - `INTEGRATION_CONTRACT.md`
   - `DELIVERABLE_MAPPING.md`
   - `PROGRESS.md`

2. Read `COPILOT_MASTER_PROMPT.md` when working in a Copilot-related workflow or when additional project context is needed.

3. Identify the relevant requirements, constraints, task scope, dependencies and existing implementation status before proposing changes.

4. Resolve conflicting instructions using the documented authority hierarchy. Never silently ignore a conflict.

5. Treat `docs/CONTRACTS.md` as immutable and authoritative.

6. Do not begin implementation if a required document is missing, unreadable or contradictory in a way that affects the task. Report the problem and ask for clarification where necessary.

7. Before implementation, provide a short Documentation Preflight summary containing:
   - Documents read.
   - Relevant requirements identified.
   - Applicable official/proposed deliverable.
   - Security and integration constraints.
   - Any conflicts or unresolved decisions.

8. Do not claim to have read a document unless its contents were actually inspected during the current task or are available in the active instruction context.

For small conversational questions or explanations that do not involve project changes, this full preflight is not required.

This requirement applies to every new substantial task, even if the same documents were read during a previous task.
