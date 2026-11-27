# Agent Orchestrator — Integration Contract

**Authority:** `docs/CONTRACTS.md` (Shared Team Contract v3.0) is authoritative. This document is an Agent-service companion and must not override or silently amend the shared contract.

## 1. Service boundary

```text
Frontend -> Backend API/Gateway -> Agent Orchestrator
                                  +-> Backend REST APIs
                                  +-> MCP server
                                  +-> RAG service
                                  +-> LLM provider
```

Frontend does not call Agent directly. Backend forwards authenticated requests and proxies SSE without buffering.

## 2. Database ownership

- Backend PostgreSQL database: `support_ai_db` (Backend-owned; Agent must not connect to it)
- Agent PostgreSQL database: `orchestrator_db`
- Backend-owned schema: `public`
- Agent-owned schema: `orchestrator`
- Agent owns and manages `orchestrator_db.orchestrator` and its migrations/checkpointer.
- Backend Alembic remains scoped to `public`.

Agent local development URL formats (this workstation's PostgreSQL server is available at `localhost:5433`; URL-encode the local password):

```env
DATABASE_URL=postgresql+asyncpg://orchestrator_user:<URL-encoded-password>@<existing-postgres-host>:<confirmed-port>/orchestrator_db
AGENT_MIGRATION_DATABASE_URL=postgresql+asyncpg://orchestrator_user:<URL-encoded-password>@<existing-postgres-host>:<confirmed-port>/orchestrator_db
```

Runtime and migration settings remain separate. The current approved topology uses `orchestrator_user` for both; do not place credentials in source control. Never connect Agent persistence to `support_ai_db`.

The repository-root `.env` is loaded by Pydantic Settings for runtime and Alembic. Pytest loads it before integration tests read `TEST_DATABASE_URL`. Exported shell variables override file values. `.env` is ignored by Git and must not be shared; `.env.example` and `.env.test.example` contain placeholders only. PostgreSQL integration tests remain opt-in when `TEST_DATABASE_URL` is absent. Current local migration revision is `20261126_01`.

Agent operational data may include LangGraph checkpoints/blobs, workflow jobs, conversation/ephemeral turn records and SSE event history. Business data remains Backend-owned.

**Hard rule:** Never query Backend-owned tables directly. Use authenticated Backend REST APIs and agreed MCP tools so Backend enforces authorization, RLS, tenant isolation and audit logging. Never query RAG tables directly.

For `langgraph-checkpoint-postgres`, verify the installed package API. Configure checkpoint connections to use `orchestrator`; if using `search_path`, apply it reliably to each connection/session, including pooled connections. Do not assume an unsupported constructor argument. Keep application and checkpointer connection configurations explicit.

## 3. Authentication and trusted context

Follow `docs/CONTRACTS.md` exactly:
- Backend-issued HS256 lean JWT.
- Lean claims: `sub`, `user_id`, `exp`, `iat`, `iss`, `aud`.
- Resolve trusted context through `GET /auth/me` according to the shared lifecycle.
- Do not assume role, org ID or permissions are embedded in JWT.
- Never trust client-supplied identity, role, org or permission.
- Never put raw JWTs in prompts, graph state, checkpoints or logs.
- Forward bearer credentials only to downstream services that require them.
- Downstream authorization is authoritative, especially for sensitive operations.

The existing `InternalGraphInput` validates/sanitizes an in-process boundary; it does not authenticate the caller. The future API/worker boundary must authenticate and resolve trusted context before creating graph input.

## 4. Error envelope

Shared contract envelope:

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Permission denied",
    "details": null
  }
}
```

Use exact shared error codes/status semantics. Map errors to safe workflow outcomes. Never expose SQL, stack traces, internal schemas, hidden notes or unauthorized data.

## 5. Backend

Backend owns authentication/context, dynamic RBAC, business records/rules, tenant isolation/RLS, official messages/notes, refunds and business audit logging. Agent orchestrates but does not replace Backend authorization. Use exact endpoint paths and payloads in canonical `docs/CONTRACTS.md`; do not invent them.

## 6. MCP

AGT-2.1 uses `langchain-mcp-adapters`. The six canonical tools are:
- `get_ticket_details`
- `search_tickets`
- `create_ticket`
- `update_ticket_status`
- `add_internal_note`
- `issue_refund`

Schemas, transport, required arguments, permission checks and error mapping come from the shared contract/current MCP implementation. Backend/MCP remains authoritative for side effects.

MCP discovery belongs inside the adapter. Discovery does not automatically make a tool available to a specialist or model. Register only the six canonical tools and enforce explicit application-level allowlists.

Proposed default mapping:
- Triage: ticket details/search/create/status update/internal note (internal note only in staff-authorized flows).
- Knowledge: no MCP tools by default.
- Billing: refund issuance only, subject to the shared approval boundary.

This mapping is an application exposure proposal, not an authorization policy. Backend/MCP authorization remains authoritative.

## 7. RAG

RAG is a separate external service, not an MCP tool. Knowledge accesses it through the provider-independent `KnowledgeRetriever` port using `retrieve_kb(query, limit=5)`. Results include `document_id`, `chunk_index`, `title`, `content`, `access_level`, `similarity_score`. Access levels include `public`, `internal_staff`, `admin_only`. RAG enforces tenant/access filtering. Shared embedding contract is `text-embedding-3-small`, 1536 dimensions.

The application retrieval boundary derives `org_id` and `authorized_kb_tiers` from validated context supplied by the authenticated runtime boundary and passes that scope separately from the query. RAG remains authoritative for enforcing both restrictions. Never trust model-generated tenant/access filters or query RAG tables directly. The external endpoint, transport and authentication details remain unresolved; no adapter is implemented.

Context Assembly and the Knowledge specialist will share this retrieval implementation. Context Assembly may perform initial relevant company-knowledge retrieval. Future on-demand retrieval for the Knowledge specialist is an application-level capability, not an MCP tool. Triage and Billing may consume supplied passages but cannot independently retrieve them.

## 8. Refund approval

The shared contract requires LangGraph interruption and explicit Org_Admin approval for refunds over `$100.00`. Backend owns approval enforcement/token creation/consumption. AGT-3.1 owns Agent interrupt, checkpoint, approval/rejection, resume and approved execution.

The adapter may be prepared before AGT-3.1, but do not invoke a refund that requires approval until the AGT-3.1 workflow is implemented. Never fabricate or bypass Backend approval tokens. Follow the shared contract for amounts that do not require HITL.

## 9. Workflow orchestration and capability boundaries

The workflow classifies requests as Conversational, Quick, Context or Deep:
- Conversational: Analyzer → lightweight conversational response → END; no Supervisor or specialist.
- Quick/Context: Analyzer → Supervisor → exactly one specialist.
- Deep target: Analyzer → Planner → validated plan → central Workflow Orchestrator → specialist tasks → Aggregator. Current implementation stops after the validated plan and does not execute tasks.

Specialists cannot invoke one another. The central orchestrator owns task scheduling/dependencies. The planner cannot grant capabilities or set trusted identity/tenant/permission data.

The orchestration engine depends on provider-independent capability interfaces. MCP and RAG adapters own transport/protocol details. Currently defined capabilities are only the six MCP tools and `retrieve_kb`. Do not invent invoice/payment lookup, reconciliation, note-reading or other operations.

See `docs/ORCHESTRATION_DESIGN.md` for detailed proposed interfaces and execution-state boundaries. This companion does not amend the shared contract.

## 10. Integration topics to verify with owners

- RAG authentication and trusted tenant/access-tier propagation.
- MCP transport/session lifecycle and preservation of the shared error envelope.
- Exact permissions for `search_tickets` and `create_ticket` as implemented by MCP.
- No note-read tool is defined; do not assume one.
- Refund approval concurrency, token replay and AGT-3.1 resume behavior.
- Cross-tenant attempts against known Org A/Org B resources.
- Whether the proposed specialist capability allowlists match team expectations.

## 11. Contract change process

If a gap is found, document the operation and exact discrepancy; contact the owning teammate; agree a team contract update. Do not silently edit `docs/CONTRACTS.md` or implement an incompatible private interpretation.
