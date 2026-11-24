# AGENTS.md — Support Agent Orchestrator

## 1. Project Overview

This repository contains the Agent Orchestration service for a multi-tenant B2B customer-support application.

The service uses:
- Python 3.12
- LangGraph for agent orchestration
- FastAPI for HTTP APIs and SSE streaming
- Pydantic and Pydantic Settings
- PostgreSQL for persistence and LangGraph checkpoints
- uv for dependency and environment management
- Docker and Docker Compose for development and deployment
- pytest for testing
- Ruff for linting and formatting

The Agent Orchestrator is an independent service. The Backend communicates with it through authenticated HTTP APIs and SSE.

## 2. Architecture Principles

Follow Hexagonal Architecture (Ports and Adapters).

- Keep core orchestration and business logic independent of infrastructure.
- Define interfaces (ports) separately from their implementations (adapters).
- Use dependency injection and configuration-based adapter selection.
- Never instantiate external infrastructure clients directly inside agents.
- Keep FastAPI as a replaceable API layer.
- Keep the LangGraph workflow independently usable.
- Avoid unnecessary abstractions and premature complexity.

External integrations must be replaceable without rewriting agent logic.

## 3. Agent Architecture

Use a central LangGraph orchestrator with individual specialist agents.

Initial agents:
- Supervisor
- Triage Agent
- Knowledge Agent
- Billing Agent

The Supervisor determines routing. The central graph controls state, execution, transitions and interruptions.

Specialist agents must not freely invoke one another.

Do not introduce individual subgraphs unless explicitly approved.

## 4. Integration Boundaries

The Agent Orchestrator integrates with:
- Backend REST APIs
- MCP server
- RAG service
- LLM providers

Business data such as users, customers, tickets, invoices and official ticket messages must be accessed through authenticated Backend APIs and agreed MCP tools.

NEVER query Backend-owned tables directly through SQL.

The Agent service owns its own operational data and persistence logic.

### Database

- PostgreSQL database: `support_ai_db`
- Backend-owned schema: `public`
- Agent-owned schema: `orchestrator`

Agent migrations and checkpoint tables must remain within `orchestrator`.

Never modify Backend-owned tables or migrations.

Configure the Python LangGraph PostgreSQL checkpointer so its tables are created in the `orchestrator` schema. Verify the actual installed library API before implementing schema configuration.

Do not assume that a constructor accepts a schema parameter without checking its documentation.

### Authentication and authorization

- Accept Backend-issued JWTs.
- Follow the shared team contract in `docs/CONTRACTS.md` when available.
- Obtain trusted user and organization context through the agreed Backend authentication interface.
- Never trust client-supplied roles or permissions.
- Never put raw JWTs into LLM prompts or LangGraph state.
- Authorization must be enforced by the appropriate downstream services.
- Account memories must never be used as authorization evidence.

## 5. Execution Architecture

Keep API and workflow execution separate.

- FastAPI API process handles requests, authentication and SSE connections.
- Worker process executes LangGraph workflows and background jobs.
- Start with PostgreSQL-backed job dispatch.
- PostgreSQL is the primary persistence layer.
- Do not introduce Redis unless a concrete requirement justifies it.

Use SSE for initial streaming transport.

Support:
- Workflow lifecycle events.
- Incremental assistant response events.
- Persisted event history.
- Event IDs and SSE reconnection.
- HITL interruptions and resumable workflows.

An SSE client disconnect must not automatically cancel the underlying workflow.

Allow only one active execution per conversation.

Keep `user_id`, `conversation_id` and LangGraph `thread_id` separate.

Initially maintain one persistent LangGraph thread per conversation.

## 6. LLM Providers

Use a provider-independent LLM adapter.

Initial provider priorities:
1. Groq
2. NVIDIA NIM
3. Mistral as a future option

Start with one configurable model shared across agents.

Never hardcode API keys or provider credentials.

Use environment-based configuration.

Do not assume every model supports structured outputs, streaming or tool calling. Verify capabilities for the selected model.

## 7. Memory Scope

Establish architecture and interfaces for:
- Individual account memory
- Conversation history
- Session state
- Conversation summaries
- Context compaction

However, full memory-system implementation is deferred until the official AGT deliverables are completed.

Do not expand initial implementation scope without approval.

## 8. Development Standards

### Python and dependencies

- Python version: `>=3.12,<3.13`
- Use uv for dependency management.
- Maintain `pyproject.toml` and `uv.lock`.
- Use `.venv` for the virtual environment.
- Do not use pip as the primary dependency manager.

### Code quality

Use Ruff for:
- Formatting
- Linting
- Import sorting

Follow:
- Type hints for public functions and interfaces.
- Clear naming and focused functions.
- Async implementations where appropriate.
- Explicit error handling.
- Pydantic models for validated input/output contracts.
- Configuration through Pydantic Settings.

Avoid unnecessary comments, excessive abstraction and duplicated logic.

### Docker

Use Docker from the beginning.

Use Docker Compose for local development.

Keep API and worker processes independently runnable.

Use environment variables and `.env.example`.

Never commit secrets or real API keys.

Coordinate PostgreSQL provisioning with the Backend team. Do not create conflicting database infrastructure.

## 9. Testing Requirements

Use:
- pytest
- pytest-asyncio
- pytest-cov

Every completed feature must have meaningful tests.

Cover:
- Normal behavior
- Edge cases
- Invalid inputs
- Failure scenarios
- Authorization and tenant-isolation assumptions
- Workflow state transitions
- Regression cases

Mock external dependencies such as Backend APIs, MCP, RAG, PostgreSQL and LLM providers where appropriate.

Test components independently, including agents, supervisor, routing, state transitions, adapters and utilities.

Maintain a centralized `tests/` structure organized by feature.

Separate unit and integration tests.

Run relevant tests before marking a feature complete.

Do not claim tests passed unless they were actually executed.

## 10. Codex Autonomy and Approval Rules

### Architecture
Propose architectural changes and wait for explicit approval before implementing them.

### Feature implementation
Once an implementation plan is approved, implement the complete coherent feature. Do not stop after every individual file, class or small change.

### Bug fixes
Investigate and fix related issues, then run regression tests without repeatedly asking for approval for every small change.

### Dependencies
Explain why a new dependency is needed before adding it.

### Security-sensitive changes
Explain the implications and obtain approval before changing established security behavior.

### Scope control
Do not implement unrelated features, speculative improvements or unnecessary abstractions.

If an important requirement is unclear, ask one focused question.

## 11. Git Rules — Mandatory

The user exclusively controls commits and pushes.

Codex MUST NOT:
- Commit changes.
- Push to GitHub.
- Merge branches.
- Rebase branches.
- Amend commits.
- Reset or rewrite Git history.
- Force push.
- Delete branches.

Codex may inspect:
- `git status`
- `git diff`
- `git log`

Codex may create or switch branches only when explicitly instructed.

Work in meaningful feature-sized batches rather than tiny changes.

After completing a task:
1. Summarize what was implemented.
2. List changed files.
3. Report tests executed and results.
4. Identify unresolved issues.
5. Suggest a meaningful commit message.

Then wait for the user to review and commit.

## 12. Official Deliverables

Preserve the official task IDs and descriptions.

| ID | Deliverable |
|---|---|
| AGT-1.1 | LangGraph State & Supervisor Node |
| AGT-1.2 | Specialized Sub-Agent Nodes |
| AGT-2.1 | RAG & MCP Tool Wiring |
| AGT-3.1 | Human-in-the-Loop Refund Gate |
| AGT-3.2 | Graceful RBAC Refusal Handling |
| AGT-4.1 | Adversarial Red-Teaming Suite |
| AGT-4.2 | Interactive Demo UI |

Implement these in their official order unless the user explicitly approves a change.

Do not silently redefine, rename or omit official deliverables.

## 13. General Working Instructions

- Read existing project documentation before making architectural decisions.
- Treat `docs/CONTRACTS.md` as the integration contract when available.
- Do not modify agreed shared contracts without approval.
- Inspect existing code before modifying it.
- Avoid overwriting existing work.
- Keep implementation and documentation synchronized.
- Prefer simple, maintainable solutions over unnecessary frameworks.
- Do not assume external services are already operational; use mock adapters during independent development when necessary.

Always prioritize correctness, security, testability and maintainability.