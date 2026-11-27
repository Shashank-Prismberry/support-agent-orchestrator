"""Persistence boundary for atomic inbound request acceptance."""

from typing import Protocol, runtime_checkable

from support_agent_orchestrator.domain.acceptance import (
    AcceptanceCandidate,
    AtomicAcceptanceRecord,
)


@runtime_checkable
class AtomicRequestAcceptor(Protocol):
    """Accept a request atomically or return the existing idempotency outcome.

    An implementation must commit the inbound Session Message, `accepted`
    Execution, idempotency record, and dispatch eligibility as one transaction.
    A new request is accepted only when no execution in the trusted conversation
    scope is in an active lifecycle state; identical retries resolve their
    idempotency record before that active-execution check.
    Duplicate comparison uses the fingerprint for the version stored on the
    original idempotency record. It must not modify that record on mismatch or
    when its stored fingerprint version is unsupported.
    """

    async def accept(self, candidate: AcceptanceCandidate) -> AtomicAcceptanceRecord: ...
