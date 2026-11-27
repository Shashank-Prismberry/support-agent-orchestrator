# Support Agent Orchestrator

Independent Python service for coordinating customer-support workflows. The
project uses LangGraph with a Ports and Adapters boundary; Backend remains the
authority for identity, authorization, business records, and side effects.

## Current implementation

- AGT-1.1 and AGT-1.2 are implemented: Supervisor routing and the Triage,
  Knowledge, and Billing specialist nodes.
- Proposed ORCH-P1 and ORCH-P2 are implemented: request-mode analysis and
  validated Deep plans. Deep execution, scheduling, and aggregation are not
  implemented.
- PostgreSQL atomic request acceptance is implemented. The initial migration
  is applied to `orchestrator_db.orchestrator` at revision `20261126_01`.
- The FastAPI transport, worker process, LangGraph PostgreSQL checkpointer,
  external MCP/RAG adapters, and full three-tier memory stores are not yet
  implemented.

See [Project Handoff](docs/PROJECT_HANDOFF.md) for the complete architecture,
database state, task status, commands, and prioritized next steps.

## Local environment

Use Python 3.12 and uv. Create `.env` from `.env.example` if it does not
already exist, then set local database credentials. The root `.env` is ignored
by Git and loaded by Pydantic Settings. Exported variables take precedence.
Copy the optional `TEST_DATABASE_URL` example into `.env` only when you intend
to run PostgreSQL integration tests against `orchestrator_db`.

```bash
uv sync
source .venv/bin/activate
uv run alembic current
uv run pytest tests/unit
uv run pytest tests/integration/test_postgres_acceptance_integration.py -v
uv run pytest
uv run ruff check src tests migrations
uv run ruff format --check src tests migrations
```

The integration suite writes and cleans up generated acceptance records in
`orchestrator_db`; run it serially and do not point `TEST_DATABASE_URL` at
Backend's `support_ai_db`. Alembic upgrade is `uv run alembic upgrade head`.

There is not yet an application/API entry point or a worker command to run.
