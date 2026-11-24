# Agent Orchestrator --- Integration Contract

**Authority:** `docs/CONTRACTS.md` (shared Team Contract v3.0) is
authoritative. This document is a service-specific companion and must
not override or silently amend the shared contract.

## 1. Service boundary

``` text
Frontend -> Backend API/Gateway -> Agent Orchestrator
                                  +-> Backend REST APIs
                                  +-> MCP server
                                  +-> RAG service
                                  +-> LLM provider
```

Frontend does not call Agent directly. Backend forwards authenticated
requests and proxies SSE without buffering.

## 2. Database ownership

Latest Backend confirmation supersedes the earlier two-logical-database
proposal: - PostgreSQL database: `support_ai_db` - Backend schema:
`public` - Agent schema: `orchestrator` - Backend provisions
`orchestrator` during database/Docker initialization. - Agent
independently manages migrations/checkpoint setup in `orchestrator`. -
Backend Alembic is scoped to `public`.

Backend-provided local development example:

``` env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/support_ai_db
```

Local defaults only; never use as production credentials.

Agent operational data: LangGraph checkpoints/blobs, workflow jobs,
conversation records/ephemeral turns, SSE event history, and future
approved memory/summary records.

Backend business data: organizations, users, customers, tickets,
official ticket messages, private notes, invoices/refunds and business
audit logs.

**Hard rule:** Never query Backend-owned tables directly. Use
authenticated Backend REST APIs and agreed MCP tools so Backend enforces
authorization, RLS, tenant isolation and audit logging. Official ticket
dialogue and private notes are synchronized through Backend APIs;
internal execution state remains in `orchestrator`.

For Python `langgraph-checkpoint-postgres`, verify the installed package
API. Configure its connections to create/query checkpoint tables in
`orchestrator`. If using `search_path`, apply it reliably to each
connection/session, including pooled connections. Do not assume an
unsupported `schema` constructor argument. Keep SQLAlchemy and
checkpointer connection configurations explicit; the app URL uses
`asyncpg`, while checkpointer may require Psycopg.

## 3. Authentication and trusted context

Follow the shared contract exactly. Known requirements: - Backend-issued
HS256 lean JWT. - Lean fields: `sub`, `user_id`, `exp`, `iat`, `iss`,
`aud`. - Obtain trusted context through `GET /auth/me` according to
agreed lifecycle. - Do not assume roles, org IDs or permissions are in
the token. - Never trust client-supplied identity, role, org or
permission. - Never put raw JWTs in prompts or graph state. - Forward
bearer credentials only when downstream services require them. -
Downstream authorization is authoritative, especially for sensitive
operations.

## 4. Error envelope

Shared contract envelope:

``` json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Permission denied",
    "details": null
  }
}
```

Contract status mapping includes 401 unauthorized, 403 forbidden, 404
missing/cross-tenant resource as defined by service contract, 422
validation, 409 conflict and 503 service unavailable.

Map errors to safe workflow outcomes. Never expose SQL, stack traces,
internal schemas, hidden notes or unauthorized data.

## 5. Backend

Backend owns authentication/context, dynamic RBAC, business
records/rules, tenant isolation/RLS, official messages/notes, refunds
and business audit logging. Agent orchestrates but does not replace
Backend authorization. Use exact endpoint paths and payloads in
canonical `docs/CONTRACTS.md`; do not invent them.

## 6. MCP

Use `langchain-mcp-adapters` as required by AGT-2.1. Canonical tools: -
`get_ticket_details` - `search_tickets` - `create_ticket` -
`update_ticket_status` - `add_internal_note` - `issue_refund`

Schemas, transport, required arguments, permission checks and error
mapping come from the shared contract/current MCP implementation.
Backend/MCP remains authoritative for business side effects.

## 7. RAG

Knowledge Agent accesses RAG through an adapter/port. Contract
operation: `retrieve_kb(query, limit=5)`. Results include `document_id`,
`chunk_index`, `title`, `content`, `access_level`, `similarity_score`.
Access levels include `public`, `internal_staff`, `admin_only`. RAG
enforces tenant/access filtering. Shared embedding contract:
`text-embedding-3-small`, 1536 dimensions. Never query RAG tables
directly or trust model-generated tenant/access filters.

## 8. HITL refund approval

AGT-3.1 requires LangGraph interruption for refunds over \$100 and
explicit Org_Admin approval. Backend owns approval enforcement/token
creation/consumption. Agent detects condition, interrupts, persists,
requests approval, resumes same workflow and invokes the approved
downstream operation using the contract-defined mechanism. Agent never
fabricates or bypasses Backend approval tokens. Backend validates
permission, token validity, single-use, expiry, binding and execution.

## 9. Streaming and execution

-   SSE is initial transport between Backend and Agent.
-   Backend proxies without buffering.
-   Workflow continues if SSE disconnects.
-   Event replay uses event IDs / `Last-Event-ID`.
-   One active execution per conversation.
-   Initially one persistent LangGraph thread per conversation.
-   `user_id`, `conversation_id`, `thread_id` remain distinct.

## 10. Integration topics to verify

Raise these with the owning teammate; do not privately redefine the
contract: - `/auth/me` context must not be treated as permanent
authority after permission changes. - Sensitive operations revalidate
authorization downstream. - MCP transport preserves the shared error
envelope. - Confirm `search_tickets` and `create_ticket` permission
requirements. - Confirm note-read contract if private note retrieval is
needed; do not assume an undocumented tool. - Confirm RAG authentication
and trusted tenant/access resolution. - Test approval concurrency and
token replay. - Test cross-tenant attempts against known Org A/Org B
resources.

## 11. Contract change process

If a gap is found: document operation and exact discrepancy; contact the
owning teammate; agree a team contract update; do not silently edit
`docs/CONTRACTS.md` or implement an incompatible private interpretation.
