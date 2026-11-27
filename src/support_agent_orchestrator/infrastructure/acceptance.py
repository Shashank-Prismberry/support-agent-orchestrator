"""PostgreSQL adapter for atomic inbound request acceptance."""

import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from sqlalchemy import insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from support_agent_orchestrator.domain.acceptance import (
    AcceptanceCandidate,
    AtomicAcceptanceRecord,
    TrustedRequestScope,
)
from support_agent_orchestrator.infrastructure.acceptance_tables import (
    executions,
    idempotency_records,
    session_messages,
)

ACTIVE_EXECUTION_STATES = (
    "accepted",
    "running",
    "waiting_for_approval",
    "cancellation_requested",
)


class _ConcurrentRequestWon(RuntimeError):
    """Signal that another transaction inserted the same scoped request key."""


class PostgresAtomicRequestAcceptor:
    """Persist acceptance records in one PostgreSQL transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def accept(self, candidate: AcceptanceCandidate) -> AtomicAcceptanceRecord:
        """Commit a new acceptance or resolve a concurrent/existing idempotency key."""

        if not candidate.fingerprints_by_version:
            raise ValueError("At least one request fingerprint is required")

        request = candidate.request
        scope = request.scope
        key_filter = (
            (idempotency_records.c.org_id == scope.org_id)
            & (idempotency_records.c.user_id == scope.user_id)
            & (idempotency_records.c.conversation_id == scope.conversation_id)
            & (idempotency_records.c.request_id == request.request_id)
        )

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    # Serialize all acceptance decisions for this trusted
                    # conversation scope across API/worker processes.
                    await _lock_conversation(session, scope)
                    existing = await _load_existing(session, key_filter)
                    if existing is not None:
                        return _resolve_existing(existing, candidate)

                    active_execution = await session.scalar(
                        select(executions.c.execution_id)
                        .where(
                            executions.c.org_id == scope.org_id,
                            executions.c.user_id == scope.user_id,
                            executions.c.conversation_id == scope.conversation_id,
                            executions.c.status.in_(ACTIVE_EXECUTION_STATES),
                        )
                        .limit(1)
                    )
                    if active_execution is not None:
                        return AtomicAcceptanceRecord(outcome="conversation_busy")

                    fingerprint_version = max(candidate.fingerprints_by_version)
                    fingerprint = candidate.fingerprints_by_version[fingerprint_version]
                    execution_id = uuid4()
                    message_id = uuid4()

                    await session.execute(
                        insert(session_messages).values(
                            message_id=message_id,
                            org_id=scope.org_id,
                            user_id=scope.user_id,
                            conversation_id=scope.conversation_id,
                            content=request.message,
                        )
                    )
                    await session.execute(
                        insert(executions).values(
                            execution_id=execution_id,
                            org_id=scope.org_id,
                            user_id=scope.user_id,
                            conversation_id=scope.conversation_id,
                            status="accepted",
                            dispatch_eligible=True,
                        )
                    )

                    claim = (
                        pg_insert(idempotency_records)
                        .values(
                            org_id=scope.org_id,
                            user_id=scope.user_id,
                            conversation_id=scope.conversation_id,
                            request_id=request.request_id,
                            execution_id=execution_id,
                            message_id=message_id,
                            fingerprint_version=fingerprint_version,
                            payload_fingerprint=fingerprint,
                        )
                        .on_conflict_do_nothing(
                            index_elements=[
                                idempotency_records.c.org_id,
                                idempotency_records.c.user_id,
                                idempotency_records.c.conversation_id,
                                idempotency_records.c.request_id,
                            ]
                        )
                        .returning(idempotency_records.c.request_id)
                    )
                    inserted_request_id = await session.scalar(claim)
                    if inserted_request_id is None:
                        raise _ConcurrentRequestWon

                    return AtomicAcceptanceRecord(
                        outcome="accepted",
                        execution_id=execution_id,
                        message_id=message_id,
                        stored_fingerprint_version=fingerprint_version,
                    )
        except _ConcurrentRequestWon:
            # The enclosing transaction rolls back the provisional message and
            # execution before resolving the winning row in a fresh transaction.
            async with self._session_factory() as session:
                async with session.begin():
                    existing = await _load_existing(session, key_filter)
                    if existing is None:
                        raise RuntimeError(
                            "The conflicting idempotency record disappeared during acceptance"
                        ) from None
                    return _resolve_existing(existing, candidate)


async def _lock_conversation(session: AsyncSession, scope: TrustedRequestScope) -> None:
    """Acquire a transaction-scoped advisory lock for a trusted conversation."""

    scope_key = json.dumps(
        [str(scope.org_id), str(scope.user_id), scope.conversation_id],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope_key, 0))"),
        {"scope_key": scope_key},
    )


async def _load_existing(
    session: AsyncSession,
    key_filter: Any,
) -> Mapping[str, Any] | None:
    result = await session.execute(select(idempotency_records).where(key_filter))
    return result.mappings().one_or_none()


def _resolve_existing(
    existing: Mapping[str, Any],
    candidate: AcceptanceCandidate,
) -> AtomicAcceptanceRecord:
    """Compare with the fingerprint version already stored for this scoped key."""

    stored_version = existing["fingerprint_version"]
    incoming_fingerprint = candidate.fingerprints_by_version.get(stored_version)
    if incoming_fingerprint is None:
        return AtomicAcceptanceRecord(
            outcome="unsupported_fingerprint_version",
            stored_fingerprint_version=stored_version,
        )
    if incoming_fingerprint != existing["payload_fingerprint"]:
        return AtomicAcceptanceRecord(outcome="conflict")
    return AtomicAcceptanceRecord(
        outcome="duplicate",
        execution_id=existing["execution_id"],
        message_id=existing["message_id"],
        stored_fingerprint_version=stored_version,
    )
