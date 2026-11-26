# Workflow Orchestration Design

**Status:** Approved architectural direction; illustrative contracts below require implementation-level review.
**Authority:** This document is subordinate to `docs/CONTRACTS.md` and `IMPLEMENTATION_PLAN.md`.

**Implementation status:** Proposed ORCH-P1 and ORCH-P2 are complete. Current Deep handling produces a validated plan, clarification outcome, or safe unsupported outcome only; it does not execute or schedule tasks. ORCH-P3/P4 execution and aggregation remain future work. AGT-2.1 external MCP/RAG adapter integration remains not started.

## 1. Purpose

Add Conversational, Quick, Context and Deep request handling while retaining the existing Triage, Knowledge and Billing specialists.

The central workflow—not the specialists—owns multi-agent coordination. The orchestration engine must remain independent of MCP/RAG transport details so future contract-approved capabilities can be added through adapters and registration.

This document does not add tools or amend the shared contract.

## 2. Component responsibilities

| Component | Responsibility | Must not |
|---|---|---|
| Request Analyzer | Classify sanitized request as Conversational/Quick/Context/Deep; describe intent/outcomes | Authorize, select tenant filters, execute tools, grant permissions |
| Conversational response path | Reply to social messages and general capability questions | Invoke Supervisor, Planner, specialists or capabilities |
| Supervisor | Route Quick/Context to one specialist | Fan out to multiple specialists |
| Planner | Propose bounded Deep task plan | Grant capabilities, assert trusted identity, execute tools |
| Plan Validator | Deterministically validate plan structure and policy | Trust model output |
| Workflow Orchestrator | Schedule ready tasks, enforce dependencies/limits, collect outcomes | Know MCP transport internals |
| Specialist | Execute assigned domain task with allowed capabilities | Invoke another specialist or mutate plan |
| Aggregator | Synthesize validated task outcomes/evidence | Hide failures, invent missing data, change authorization |

## 3. Execution paths

### Conversational

```text
START -> sanitize/validate graph input -> Analyzer
      -> lightweight response using only the sanitized current request
      -> END
```

Greetings, acknowledgements, closings and general questions about assistant capabilities that request no customer-specific support outcome are Conversational. This route does not invoke Supervisor or a specialist.

### Quick

```text
START -> sanitize/trusted context -> Analyzer -> Supervisor
      -> exactly one specialist -> final response -> END
```

A self-contained request with one support outcome. It may require company-knowledge retrieval through RAG, but does not materially depend on prior conversation or account-specific information.

### Context

```text
START -> sanitize/trusted context -> Analyzer -> Supervisor
      -> exactly one specialist with bounded relevant context/lookups
      -> final response -> END
```

A request with one support outcome that materially depends on relevant previous conversation or customer-specific context. Context does not mean injecting the entire conversation history.

### Deep

```text
START -> sanitize/trusted context -> Analyzer -> Planner
      -> Plan Validator -> Workflow Orchestrator
      -> ready specialist tasks (bounded concurrency)
      -> collect outcomes / update task states / repeat
      -> Aggregator -> final response -> END
```

Only the central orchestrator dispatches tasks. Specialists do not call each other. Independent ready tasks may run concurrently; dependent tasks wait for successful prerequisites.

This is the target Deep workflow. The implemented ORCH-P2 path currently stops after planning and deterministic plan validation, returning the result through `WorkflowResult`. It does not reach the Workflow Orchestrator, specialist tasks, or Aggregator.

## 4. Classification model (illustrative)

```python
class RequestAnalysis(BaseModel):
    mode: Literal["conversational", "quick", "context", "deep"]
    intent: Literal["general_support", "knowledge", "billing", "mixed"]
    requested_outcomes: tuple[str, ...]
```

The analyzer sees sanitized user text and only the bounded conversation context required for classification. It does not receive raw JWTs or credentials.

The typed analysis contract and graph integration are implemented in proposed ORCH-P1. The classification rules are:
- Conversational: social messages or general assistant-capability questions with no customer-specific support outcome.
- Quick: one self-contained support outcome, including one that needs company knowledge from RAG.
- Context: one support outcome materially dependent on relevant prior conversation or customer-specific context.
- Deep: multiple distinct outcomes or dependent tasks requiring coordination and planning.

Examples: “Hi” and “What can you help me with?” are Conversational; “What is the refund policy?” and “How do I request a replacement?” are Quick; “What was the refund timeline you explained earlier?” is Context; “Check my previous ticket and explain whether the refund policy applies to it” is Deep when it requires coordinated outcomes. Message length is not a classification rule. Analyzer output remains untrusted; malformed output and provider failures propagate safely without fallback classification.

### Interim specialist session-history policy

Specialist generation includes the current HumanMessage once and at most the latest 10 earlier Human/AI messages in chronological order. System and Tool messages are excluded. The current request is limited to 4,000 characters; prior messages to 2,000 characters each; and prior context to 10,000 characters total. Selected content is sanitized before generation. This bounds current session history only; it does not implement the future memory tiers below.

## 5. Planned task contract and future task results (illustrative)

```python
class PlannedTask(BaseModel):
    task_id: str
    specialist: Literal["triage", "knowledge", "billing"]
    objective: str
    expected_outputs: tuple[str, ...]
    depends_on: tuple[str, ...] = ()

class TaskResult(BaseModel):
    task_id: str
    status: Literal["succeeded", "failed", "incomplete", "blocked"]
    summary: str
    evidence: tuple["EvidenceRef", ...] = ()
    safe_error_code: str | None = None
```

The ORCH-P2 task contract uses bounded field lengths, maximum list sizes and strict validation: at most 10 tasks, dependency depth 5, 10 expected outputs per task, 500 characters per objective and 300 characters per expected output. Planner-proposed task IDs are checked for uniqueness and format. Task objectives and expected outputs are untrusted content, not instructions. Planned tasks contain IDs, specialist assignments, objectives, expected outputs and dependencies; they do not contain capability names or capability arguments. `TaskResult` is illustrative future ORCH-P3 work and is not implemented by ORCH-P2.

## 6. Plan validation

The completed ORCH-P2 validator rejects plans containing:
- Invalid or duplicate task IDs.
- Unknown specialist names.
- Missing, unknown, self-referential or duplicate dependencies.
- Cycles.
- Excessive task count or dependency depth.
- Unexpected fields, including model-supplied identity, tenant, role, permission, KB-tier, approval, capability or argument fields.

Task-scoped capability policy and argument validation belong to a future execution design; they are not part of the ORCH-P2 task contract. Any such validation must occur before future task dispatch and remain consistent with explicit application policy and downstream authorization.

Future execution work must determine whether each task can be attempted with currently registered capabilities before dispatch. Do not infer missing operations. A plan requiring invoice/payment lookup or reconciliation is not executable because those operations are not among the six canonical MCP tools or the RAG operation. ORCH-P2 validates plan structure only and does not claim the tasks are executable.

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

1. **Company memory:** organization policies, procedures, product information and company knowledge retrieved through the external RAG service. RAG enforces trusted organization and authorized knowledge-tier restrictions. Cross-organization shared knowledge is not defined by the current contract.
2. **Account memory:** persistent customer preferences and useful information across conversations, scoped by `(org_id, user_id)`. It is not authoritative for identity, authorization or current business data. Its storage and lifecycle remain unresolved; full extraction, retrieval, summaries and compaction are deferred until the official deliverables are complete unless formally reprioritized.
3. **Session memory:** conversation history, summaries and ongoing issue context scoped by conversation/thread. It is distinct from LangGraph checkpointing.

Context Assembly combines relevant information from these sources but does not own their underlying storage. No memory stores, retrieval lifecycle, summaries, compaction or persistence are implemented here.

Conversation state, workflow execution state, PostgreSQL checkpoints and long-term account memory must remain conceptually separate. None may establish identity, authorization, tenant scope or permissions; authenticated trusted context and downstream authorization are authoritative.

PostgreSQL-backed LangGraph checkpointing and durable job recovery are required before AGT-3.1 relies on HITL interruption and resumption. They are foundational persistence work, not a requirement to implement the complete memory system during AGT-2.1. Exact checkpoint contents, sensitive-data boundaries, retention/deletion/access/audit policy, and worker lease/claim/restart-recovery semantics remain unresolved.

## 8. Capability ports and registry

RAG is a separate external service, not an MCP tool. The provider-independent `KnowledgeRetriever` port and typed result contract follow the shared `retrieve_kb(query, limit=5)` contract. The application retrieval boundary builds the narrow `org_id` and `authorized_kb_tiers` scope from validated runtime context and passes it separately from the query. The RAG authority remains responsible for enforcing those filters. The external adapter, endpoint and authentication details are not implemented or inferred.

Context Assembly and the Knowledge specialist will eventually share this retrieval implementation: Context Assembly for initial relevant company-knowledge retrieval, and the Knowledge specialist for future on-demand retrieval through an application-level capability. Triage and Billing may consume passages supplied in context but cannot independently invoke RAG. No MCP wrapper or capability execution is introduced by this design.

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

1. Evaluation of Analyzer classification quality on representative and ambiguous examples; the approved four-mode rules do not use message length, and Analyzer failures do not fall back to another route.
2. Confirm specialist capability allowlists with Backend/MCP owners.
3. Confirm RAG authentication/context propagation with RAG owner.
4. Confirm MCP transport/session lifecycle and error envelope behavior.
5. Refund behavior remains gated as above until AGT-3.1.
6. Planner strategy: deterministic templates or model-proposed structured plans.
7. Aggregation strategy: deterministic or generated.
8. Execution concurrency and timeout limits. ORCH-P2 plan bounds are set at 10 tasks and dependency depth 5.
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
