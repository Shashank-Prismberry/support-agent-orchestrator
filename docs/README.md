# Shared Contracts and Documentation Ownership

## `CONTRACTS.md` is authoritative

`docs/CONTRACTS.md` is the Shared Team Contract v3.0 maintained through team agreement.

**Do not regenerate, replace, casually edit, reformat or independently reinterpret it.** Keep the canonical file byte-for-byte unchanged. If a gap or conflict is found, document it and raise it with the owning teammate.

`INTEGRATION_CONTRACT.md` is the Agent-service companion. If it conflicts with the shared contract, the shared contract wins; raise the discrepancy rather than silently changing either document.

## Related documents

- `AGENTS.md` — primary persistent instructions for Codex.
- `IMPLEMENTATION_PLAN.md` — engineering plan and architecture decisions.
- `docs/ORCHESTRATION_DESIGN.md` — detailed Quick/Context/Deep and workflow orchestration design.
- `DELIVERABLE_MAPPING.md` — official AGT tasks and separately labelled proposed orchestration work.
- `INTEGRATION_CONTRACT.md` — Agent integration boundaries.
- `PROGRESS.md` — current project status.
- `PROJECT_HANDOFF.md` — platform-independent implementation, database, setup, and next-step snapshot.
- `COPILOT_MASTER_PROMPT.md` — reusable Copilot/session context.
- `.github/copilot-instructions.md` — Copilot compatibility instructions, if present.

## Documentation responsibilities

- Shared contract: authoritative team-wide interfaces and security rules.
- Implementation plan: system architecture, flows, sequencing and deferred decisions.
- Orchestration design: detailed planner/scheduler/task/result design.
- Deliverable mapping: official task scope and acceptance criteria; proposed work clearly separated.
- Integration contract: service-specific view of Backend/MCP/RAG boundaries.
- Progress: actual completed/in-progress/pending status.
- AGENTS/Copilot instructions: working rules and architecture context for coding assistants.

Avoid copying the same detailed design into every file. Link to the owning document instead.

Update `PROGRESS.md` as work is completed. Update the plan/design/mapping only when an approved architecture or scope decision changes.
