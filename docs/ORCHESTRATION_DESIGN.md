# Workflow Orchestration Design

**Status:** Approved architectural direction; illustrative contracts below require implementation-level review.
**Authority:** This document is subordinate to `docs/CONTRACTS.md` and `IMPLEMENTATION_PLAN.md`.

## 1. Purpose

Add Quick, Context and Deep request handling while retaining the existing Triage, Knowledge and Billing specialists.

The central workflow—not the specialists—owns multi-agent coordination. The orchestration engine must remain independent of MCP/RAG transport details so future contract-approved capabilities can be added through adapters and registration.

This document does not add tools or amend the shared contract.

## 2. Component responsibilities

| Component | Responsibility | Must not |
|---|---|---|
| Request Analyzer | Classify sanitized request as Quick/Context/Deep; describe intent/outcomes | Authorize, select tenant filters, execute tools, grant permissions |
| Supervisor | Route Quick/Context to one specialist | Fan out to multiple specialists |
| Planner | Propose bounded Deep task plan | Grant capabilities, assert trusted identity, execute tools |
| Plan Validator | Deterministically validate plan structure and policy | Trust model output |
| Workflow Orchestrator | Schedule ready tasks, enforce dependencies/limits, collect outcomes | Know MCP transport internals |
| Specialist | Execute assigned domain task with allowed capabilities | Invoke another specialist or mutate plan |
| Aggregator | Synthesize validated task outcomes/evidence | Hide failures, invent missing data, change authorization |

## 3. Execution paths

### Quick

```text
START -> sanitize/trusted context -> Analyzer -> Supervisor
      -> exactly one specialist -> final response -> END
```

A direct request answerable by one specialist with minimal context and no multi-task plan.

### Context

```text
START -> sanitize/trusted context -> Analyzer -> Supervisor
      -> exactly one specialist with bounded relevant context/lookups
      -> final response -> END
```

A request needing relevant conversation context and/or permitted lookups, but still answerable by one specialist. Context does not mean injecting the entire conversation history.

### Deep

```text
START -> sanitize/trusted context -> Analyzer -> Planner
      -> Plan Validator -> Workflow Orchestrator
      -> ready specialist tasks (bounded concurrency)
      -> collect outcomes / update task states / repeat
      -> Aggregator -> final response -> END
```

Only the central orchestrator dispatches tasks. Specialists do not call each other. Independent ready tasks may run concurrently; dependent tasks wait for successful prerequisites.

## 4. Classification model (illustrative)

```python
class RequestAnalysis(BaseModel):
    mode: Literal["quick", "context", "deep"]
    intent: Literal["general_support", "knowledge", "billing", "mixed"]
    requested_outcomes: tuple[str, ...]
```

The analyzer sees sanitized user text and only the bounded conversation context required for classification. It does not receive raw JWTs or credentials.

The project must define concrete examples and thresholds before implementation. A malformed/ambiguous analysis must take a conservative path; it must never trigger an unvalidated Deep plan or side effect.

## 5. Planned task and result contracts (illustrative)

```python
class PlannedTask(BaseModel):
    task_id: str
    specialist: Literal["triage", "knowledge", "billing"]
    objective: str
    depends_on: tuple[str, ...] = ()
    capability_names: tuple[str, ...] = ()

class TaskResult(BaseModel):
    task_id: str
    status: Literal["succeeded", "failed", "incomplete", "blocked"]
    summary: str
    evidence: tuple["EvidenceRef", ...] = ()
    safe_error_code: str | None = None
```

Implementation should use bounded field lengths, maximum list sizes and strict validation. Prefer server-generated task IDs or validate planner-proposed IDs against uniqueness and format rules. Task objectives and dependency summaries are untrusted content, not instructions.

## 6. Plan validation

Reject plans containing:
- Unknown or duplicate task IDs.
- Unknown specialist names.
- Unknown capabilities or capabilities outside the specialist's static allowlist.
- Missing, unknown, self-referential or duplicate dependencies.
- Cycles.
- Excessive task count or dependency depth.
- Malformed/out-of-contract arguments.
- Model-supplied identity, tenant, role, permission, KB-tier, approval or credential fields.

Validate that every task is relevant to the requested outcomes and can be attempted with currently registered capabilities. Do not infer missing operations. A plan requiring invoice/payment lookup or reconciliation is not executable because those operations are not among the six canonical MCP tools or the RAG operation.

## 7. Execution state and conversation state

Keep the existing four-field `AgentState` as the conversation state:
`messages`, `user_context`, `active_agent`, `approval_status`.

Use a separate typed execution-state envelope for one workflow run. Illustrative shape:

```python
class ExecutionState(TypedDict):
    analysis: RequestAnalysis
    plan: list[PlannedTask]
    task_status: dict[str, str]
    task_results: dict[str, TaskResult]
    final_response: str | None
```

The actual LangGraph state/reducer design must account for parallel writes. Updates should merge deterministically; conflicting updates for the same task must fail safely. Avoid broad mutable shared dictionaries where task updates can race.

Persist only bounded task summaries/evidence references required for execution and approved resumption. Never persist raw JWTs, bearer tokens, credentials, full unbounded MCP payloads or unnecessary PII. Checkpoint access and retention need an explicit policy.

### Memory and persistence boundaries

The architecture preserves three conceptually separate tiers:

1. **Knowledge memory:** organization-scoped knowledge accessed only through the existing RAG operation. RAG enforces trusted tenant and access-tier filtering. Cross-organization shared knowledge is not defined by the current contract.
2. **Individual/account memory:** cross-conversation information about an individual user. Its full extraction, retrieval, summarization and compaction are deferred until the official deliverables are complete unless formally reprioritized. Ownership and storage remain unresolved.
3. **Session/conversation memory:** bounded active conversation context, including `AgentState` and future summaries/compaction.

Conversation state, workflow execution state, PostgreSQL checkpoints and long-term account memory must remain conceptually separate. None may establish identity, authorization, tenant scope or permissions; authenticated trusted context and downstream authorization are authoritative.

PostgreSQL-backed LangGraph checkpointing and durable job recovery are required before AGT-3.1 relies on HITL interruption and resumption. They are foundational persistence work, not a requirement to implement the complete memory system during AGT-2.1. Exact checkpoint contents, sensitive-data boundaries, retention/deletion/access/audit policy, and worker lease/claim/restart-recovery semantics remain unresolved.

## 8. Capability ports and registry

Illustrative provider-independent interfaces:

```python
class Capability(Protocol):
    name: str
    async def invoke(self, request: CapabilityRequest) -> CapabilityResult: ...

class CapabilityRegistry(Protocol):
    def resolve(self, name: str) -> Capability: ...

class SpecialistExecutor(Protocol):
    async def execute(self, request: SpecialistTaskRequest) -> SpecialistTaskResult: ...
```

These are conceptual contracts, not a requirement to create one abstraction per class. Keep the actual interface surface minimal.

Adapters own:
- MCP session/transport and tool discovery.
- RAG HTTP transport.
- Credential forwarding where required.
- Input/output schema validation.
- Shared error-envelope mapping.
- Connection lifecycle and timeouts.

The scheduler and planner must not import MCP SDK types. Register capabilities explicitly at application startup. MCP discovery does not imply permission to expose a tool to a model.

Trusted identity/context and credentials are supplied separately as internal runtime context where required; they are not serialized into task state or prompts. Planner output cannot alter the registry or caller context.

## 9. Current capability inventory and proposed allowlists

The only currently defined capabilities are:

| Capability | Proposed specialist | Notes |
|---|---|---|
| `get_ticket_details` | Triage | Backend enforces ticket visibility and tenant ownership |
| `search_tickets` | Triage | Contract query/status/limit; max limit 50 |
| `create_ticket` | Triage | Side effect; Backend authorizes |
| `update_ticket_status` | Triage | Backend enforces permission and lifecycle |
| `add_internal_note` | Triage, staff workflow only | Staff permission required; customer forbidden |
| `issue_refund` | Billing | Backend enforces permission, amount and approval token |
| `retrieve_kb` | Knowledge | RAG enforces tenant and authorized KB tier filtering |

The specialist mapping is an application-level default proposal. It does not replace downstream authorization. Do not automatically expose discovered tools. Any change to allowlists requires review.

No note-read, invoice-read, payment-read or reconciliation capability is defined here. Do not invent one or query Backend tables directly.

## 10. Refund boundary

The shared contract requires LangGraph interruption and explicit Org_Admin approval for `issue_refund` amounts over `$100.00`; Backend creates and validates the single-use approval token.

Before AGT-3.1:
- The adapter and request/response contracts may be prepared.
- Do not call `issue_refund` when the contract requires approval.
- Do not create/fabricate approval tokens or substitute another approval process.
- Return a safe outcome indicating the approval workflow is not yet available.
- Do not implement interrupt/checkpoint/approval/resume as part of the orchestration extension; AGT-3.1 owns it.

AGT-3.1 must rely on the approved PostgreSQL checkpoint and durable recovery foundation when it implements interruption/resumption. ORCH-P1 through ORCH-P4 remain proposed workstreams and are not mandatory prerequisites for AGT-3.1 unless formally approved.

## 11. Scheduling and failure semantics

A task is ready only when every dependency has succeeded. Run independent ready tasks concurrently up to a configured limit. Enforce per-operation timeouts and an overall workflow deadline.

On failure:
- Mark the task failed/incomplete with a safe error code.
- Mark dependents blocked/incomplete.
- Continue unrelated tasks where safe.
- Do not retry permission/validation/conflict failures.
- Retry transient read-only failures only within a configured bound.
- Never blindly retry side effects; use contract-supported idempotency.
- Stop when all tasks are terminal or a workflow bound is reached.

Cancellation should prevent further dispatch where possible but cannot reverse completed external side effects.

## 12. Aggregation

The aggregator receives only validated bounded results/evidence. It should:
- Preserve source attribution.
- Distinguish observed facts from inference.
- Identify conflicting evidence.
- State which tasks failed or sources were unavailable.
- Avoid presenting a partial investigation as complete.
- Never invent results for unavailable capabilities.

Decision still required: deterministic aggregation versus a final provider-backed generation call. If generation is used, it must not receive credentials or untrusted full payloads and cannot change workflow state or authorization.

## 13. Security

- API/worker boundary authenticates Backend JWT and resolves `/auth/me` before constructing `InternalGraphInput`.
- `InternalGraphInput` validation is not authentication provenance.
- Never accept tenant/permission/KB-tier claims from user or model output.
- RAG receives trusted context; RAG enforces `org_id` and `authorized_kb_tiers`.
- Backend/MCP remains authoritative for business reads, writes and side effects.
- Treat retrieved documents, ticket text and tool results as untrusted evidence.
- Bound all planner output, tool arguments, task results and retrieved text.
- Never put raw credentials in graph state, prompts, logs or checkpoints.

## 14. Decisions to finalize before implementation

1. Quick/Context/Deep rubric, examples and fallback.
2. Confirm specialist capability allowlists with Backend/MCP owners.
3. Confirm RAG authentication/context propagation with RAG owner.
4. Confirm MCP transport/session lifecycle and error envelope behavior.
5. Refund behavior remains gated as above until AGT-3.1.
6. Planner strategy: deterministic templates or model-proposed structured plans.
7. Aggregation strategy: deterministic or generated.
8. Initial max tasks, depth, concurrency and timeout limits.
9. Cross-organization shared-knowledge behavior; the current RAG contract is organization-scoped.
10. Tier 2 account-memory ownership and storage.
11. Memory/checkpoint retention, deletion, access and audit policy.
12. Exact checkpoint contents and sensitive-data boundaries.
13. Durable worker lease, claim and restart-recovery semantics.
14. Formal team task IDs/owners for the proposed orchestration work.

## 15. Test matrix

- Analyzer: all modes, ambiguous requests, malformed output, prompt injection, bounded context.
- Planner: invalid output, unsupported capabilities, malicious objectives, oversized plans.
- Validator: duplicate IDs, unknown/self dependencies, cycles, unknown specialists/tools, allowlist violations.
- Scheduler: dependency order, parallel independent tasks, concurrency cap, deadline, cancellation, failed prerequisites, independent task continuation.
- State: deterministic parallel merges, conflicting updates, no credentials/tenant claims in state.
- Specialists: task-scoped input, correct allowlist, no specialist-to-specialist calls.
- Aggregator: attribution, conflicts, partial results, missing capability, no unsupported claims.
- Adapters: schema validation, timeout, unavailable service, shared error mapping, no direct SQL.
- Security: cross-tenant negative tests, prompt/result injection, no raw JWT/secrets, no refund execution before required approval.
- Regression: preserve AGT-1.1/AGT-1.2 behavior and invocation contract.
