# Copilot Instructions --- Support Agent Orchestrator

For ChatGPT Codex, root `AGENTS.md` is primary. These instructions
support GitHub Copilot.

Before substantial work, read `AGENTS.md`, `IMPLEMENTATION_PLAN.md`,
`docs/CONTRACTS.md`, `INTEGRATION_CONTRACT.md`, `DELIVERABLE_MAPPING.md`
and `PROGRESS.md`.

## Mandatory boundaries

-   Independent Agent Orchestrator service; not the Backend.
-   Hexagonal Architecture; graph core independent of
    FastAPI/infrastructure.
-   One database `support_ai_db`; Backend owns `public`, Agent owns
    `orchestrator`.
-   Never query Backend business tables directly. Use authenticated
    APIs/MCP.
-   Follow shared Team Contract v3.0; do not redefine it.
-   Never trust client/model-supplied identity, tenant, role or
    permissions.
-   Never place raw JWTs/secrets in prompts or graph state.
-   Separate API and worker processes; PostgreSQL-backed job dispatch
    initially.
-   SSE initially, with persisted event replay; disconnect does not
    cancel execution.
-   One active workflow per conversation.
-   User owns all Git history operations.

## Engineering standards

Python 3.12, uv, Ruff, pytest/pytest-asyncio/pytest-cov, Pydantic
Settings and Docker Compose. Add tests with each feature; mock external
services in unit tests. Test failures, edge cases, permissions and
tenant isolation. Explain dependency additions. Ask before
architecture/security changes. Implement approved features as coherent
batches. Do not claim tests passed unless executed.

## Official task sequence

AGT-1.1 LangGraph State & Supervisor Node; AGT-1.2 Specialized Sub-Agent
Nodes; AGT-2.1 RAG & MCP Tool Wiring; AGT-3.1 Human-in-the-Loop (HITL)
Refund Gate; AGT-3.2 Graceful RBAC Refusal Handling; AGT-4.1 Adversarial
Red-Teaming Suite; AGT-4.2 Interactive Demo UI.

Never commit, push, merge, rebase, amend, reset or rewrite Git history.
Do not create/switch branches unless explicitly told.
