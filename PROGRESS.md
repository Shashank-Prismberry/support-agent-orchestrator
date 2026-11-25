# Project Progress — Support Agent Orchestrator

**Last updated:** 2026-11-25
**Overall status:** AGT-1.1 and AGT-1.2 complete; AGT-2.1 not started
**Current official deliverable:** AGT-2.1 — RAG & MCP Tool Wiring
**Architecture direction:** Quick/Context/Deep workflow orchestration approved as a project direction; implementation not started.

## Decisions established

- Independent Agent Orchestrator service.
- Frontend → Backend → Agent; Backend proxies SSE.
- Separate API and worker processes/containers.
- PostgreSQL-backed job dispatch initially; no Redis initially.
- Database `support_ai_db`; Backend schema `public`; Agent schema `orchestrator`.
- Backend provisions `orchestrator`; Agent manages its schema migrations/checkpointer.
- Business data only through authenticated Backend APIs and agreed MCP tools.
- Hexagonal Architecture and replaceable ports/adapters.
- Central LangGraph workflow with Triage, Knowledge and Billing specialists.
- Specialists do not invoke one another; central workflow owns multi-specialist execution.
- Request Analyzer classifies Quick/Context/Deep.
- Quick/Context use Supervisor → exactly one specialist.
- Deep uses Planner → validated plan → central scheduler → specialist tasks → Aggregator.
- Capability layer is independent of MCP transport; only six contract-defined MCP tools and `retrieve_kb` are currently in scope.
- Backend/MCP authorization and tenant isolation remain authoritative.
- Refund approval requirements remain intact; AGT-3.1 owns HITL interrupt/checkpoint/approval/resume.
- SSE event replay/reconnection; disconnect does not cancel workflow.
- One active execution per conversation; one persistent LangGraph thread per conversation initially.
- Keep `user_id`, `conversation_id`, `thread_id` distinct.
- Three-tier memory architecture: organization-scoped RAG knowledge; deferred individual/account memory across conversations; and bounded session/conversation memory with future summaries/compaction.
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
- AGT-1.1 and AGT-1.2 were merged into `main` by the user. Current working branch for next work was created from updated main: `feature/AGT-2.1-rag-mcp-tool-wiring`.

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
| ORCH-P1 | Request Analyzer and Quick/Context/Deep routing | Not started |
| ORCH-P2 | Deep Planner and plan/DAG validation | Not started |
| ORCH-P3 | Execution state, scheduler and specialist task interface | Not started |
| ORCH-P4 | Aggregation, partial failures and reliability | Not started |

## Not yet confirmed / not done

- Live integration with Backend, MCP or RAG.
- AGT-2.1 adapters and capability registration.
- Request Analyzer, Planner, scheduler and Aggregator implementation.
- Formal team assignment/IDs for ORCH-P1–P4.
- Final Quick/Context/Deep classification rubric.
- Final RAG authentication/context propagation details with RAG owner.
- Final MCP transport/session lifecycle details with MCP owner.
- Final execution checkpoint retention/access policy.
- Cross-organization shared-knowledge behavior.
- Tier 2 account-memory ownership and storage.
- Memory/checkpoint retention, deletion, access and audit policy.
- Exact checkpoint contents and sensitive-data boundaries.
- Durable worker lease, claim and restart-recovery semantics.
- Dockerfiles/Compose and deployment setup (verify current workspace before changing status).

Do not mark work complete unless actually implemented and verified.

## Immediate next steps

1. Reconcile and review project documentation.
2. Confirm any remaining team-owned decisions: capability allowlists, RAG context propagation, MCP transport/error behavior, formal ORCH task ownership and classification rubric.
3. Finalize AGT-2.1 implementation design and dependencies.
4. Implement AGT-2.1 capability contracts/adapters using only defined operations; do not expand it into the complete persistence or memory system.
5. Establish the approved PostgreSQL checkpointing and durable recovery foundation before AGT-3.1 depends on HITL interruption/resumption.
6. Plan ORCH-P1 through ORCH-P4 as separately approved workstreams; they are not mandatory prerequisites for AGT-3.1.

## Update rule

For each completed deliverable/workstream record:
- implementation summary,
- changed files,
- tests actually run/results,
- integration blockers,
- unresolved decisions,
- suggested commit message.

The user commits and pushes manually.
