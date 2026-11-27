from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from support_agent_orchestrator.application.acceptance import (
    CURRENT_CANONICALIZATION_VERSION,
    ConversationBusyError,
    RequestAcceptanceConflictError,
    RequestAcceptanceService,
    UnsupportedFingerprintVersionError,
)
from support_agent_orchestrator.domain.acceptance import (
    AcceptanceCandidate,
    AtomicAcceptanceRecord,
    InboundRequest,
    TrustedRequestScope,
)
from support_agent_orchestrator.ports.acceptance import AtomicRequestAcceptor
from support_agent_orchestrator.ports.analysis import MAX_CURRENT_REQUEST_CHARACTERS

EXECUTION_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
MESSAGE_ID = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
ORG_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("aaaaaaa1-1111-1111-1111-111111111111")


def make_request(
    *,
    org_id: UUID = ORG_ID,
    user_id: UUID = USER_ID,
    conversation_id: str = "conversation-a",
    message: str = "Please help with my support issue.",
) -> InboundRequest:
    return InboundRequest(
        scope=TrustedRequestScope(
            org_id=org_id,
            user_id=user_id,
            conversation_id=conversation_id,
        ),
        request_id="caller-request-1",
        message=message,
    )


class FakeAtomicAcceptor:
    """Model atomic outcomes; this does not prove database transaction behavior."""

    def __init__(self) -> None:
        self.records: dict[tuple[UUID, UUID, str, str], tuple[int, str, UUID, UUID]] = {}
        self.turns: list[tuple[UUID, str]] = []
        self.executions: list[UUID] = []
        self.dispatch_eligible: set[UUID] = set()
        self.force_failure = False
        self.calls = 0

    async def accept(self, candidate: AcceptanceCandidate) -> AtomicAcceptanceRecord:
        self.calls += 1
        request = candidate.request
        scope = request.scope
        key = (scope.org_id, scope.user_id, scope.conversation_id, request.request_id)
        existing = self.records.get(key)

        if existing is not None:
            version, fingerprint, execution_id, message_id = existing
            incoming = candidate.fingerprints_by_version.get(version)
            if incoming is None:
                return AtomicAcceptanceRecord(
                    outcome="unsupported_fingerprint_version",
                    stored_fingerprint_version=version,
                )
            if incoming != fingerprint:
                return AtomicAcceptanceRecord(outcome="conflict")
            return AtomicAcceptanceRecord(
                outcome="duplicate",
                execution_id=execution_id,
                message_id=message_id,
                stored_fingerprint_version=version,
            )

        version = max(candidate.fingerprints_by_version)
        execution_id = uuid4()
        message_id = uuid4()
        staged_record = (
            version,
            candidate.fingerprints_by_version[version],
            execution_id,
            message_id,
        )
        if self.force_failure:
            raise RuntimeError("acceptance transaction failed")

        # Publish the staged acceptance as one fake commit.
        self.records[key] = staged_record
        self.turns.append((message_id, request.message))
        self.executions.append(execution_id)
        self.dispatch_eligible.add(execution_id)
        return AtomicAcceptanceRecord(
            outcome="accepted",
            execution_id=execution_id,
            message_id=message_id,
            stored_fingerprint_version=version,
        )


@pytest.mark.asyncio
async def test_first_request_acceptance_creates_execution_turn_and_dispatch_eligibility() -> None:
    acceptor = FakeAtomicAcceptor()

    result = await RequestAcceptanceService(acceptor).accept(make_request())

    assert isinstance(acceptor, AtomicRequestAcceptor)
    assert result.duplicate is False
    assert result.execution_id in acceptor.executions
    assert acceptor.turns == [(result.message_id, "Please help with my support issue.")]
    assert result.execution_id in acceptor.dispatch_eligible
    assert len(acceptor.records) == 1


@pytest.mark.asyncio
async def test_identical_duplicate_returns_original_execution_and_turn() -> None:
    acceptor = FakeAtomicAcceptor()
    service = RequestAcceptanceService(acceptor)
    first = await service.accept(make_request())

    duplicate = await service.accept(make_request())

    assert duplicate.duplicate is True
    assert duplicate.execution_id == first.execution_id
    assert duplicate.message_id == first.message_id
    assert len(acceptor.executions) == 1
    assert len(acceptor.turns) == 1


@pytest.mark.asyncio
async def test_same_scoped_request_id_with_different_payload_conflicts_without_mutation() -> None:
    acceptor = FakeAtomicAcceptor()
    service = RequestAcceptanceService(acceptor)
    first = await service.accept(make_request())
    original_records = dict(acceptor.records)
    original_turns = list(acceptor.turns)

    with pytest.raises(RequestAcceptanceConflictError):
        await service.accept(make_request(message="A different request."))

    assert acceptor.records == original_records
    assert acceptor.turns == original_turns
    assert acceptor.executions == [first.execution_id]


@pytest.mark.asyncio
async def test_different_trusted_scopes_do_not_collide() -> None:
    acceptor = FakeAtomicAcceptor()
    service = RequestAcceptanceService(acceptor)

    first = await service.accept(make_request(conversation_id="conversation-a"))
    second = await service.accept(make_request(conversation_id="conversation-b"))

    assert first.execution_id != second.execution_id
    assert first.duplicate is False
    assert second.duplicate is False
    assert len(acceptor.executions) == 2


@pytest.mark.asyncio
async def test_identical_request_does_not_collide_across_organizations() -> None:
    acceptor = FakeAtomicAcceptor()
    service = RequestAcceptanceService(acceptor)

    first = await service.accept(make_request())
    second = await service.accept(make_request(org_id=UUID("22222222-2222-2222-2222-222222222222")))

    assert first.duplicate is False
    assert second.duplicate is False
    assert first.execution_id != second.execution_id


@pytest.mark.asyncio
async def test_identical_request_does_not_collide_across_users() -> None:
    acceptor = FakeAtomicAcceptor()
    service = RequestAcceptanceService(acceptor)

    first = await service.accept(make_request())
    second = await service.accept(
        make_request(user_id=UUID("bbbbbbb1-1111-1111-1111-111111111111"))
    )

    assert first.duplicate is False
    assert second.duplicate is False
    assert first.execution_id != second.execution_id


@pytest.mark.asyncio
async def test_identical_request_does_not_collide_across_conversations() -> None:
    acceptor = FakeAtomicAcceptor()
    service = RequestAcceptanceService(acceptor)

    first = await service.accept(make_request())
    second = await service.accept(make_request(conversation_id="conversation-b"))

    assert first.duplicate is False
    assert second.duplicate is False
    assert first.execution_id != second.execution_id


def test_unsupported_configured_canonicalization_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="canonicalization version is not supported"):
        RequestAcceptanceService(
            FakeAtomicAcceptor(),
            supported_versions=(CURRENT_CANONICALIZATION_VERSION, 2),
        )


@pytest.mark.asyncio
async def test_oversized_request_is_rejected_before_persistence() -> None:
    acceptor = FakeAtomicAcceptor()

    with pytest.raises(ValueError, match="exceeds the size limit"):
        await RequestAcceptanceService(acceptor).accept(
            make_request(message="x" * (MAX_CURRENT_REQUEST_CHARACTERS + 1))
        )

    assert acceptor.calls == 0


@pytest.mark.asyncio
async def test_unsupported_stored_fingerprint_version_fails_without_mutation() -> None:
    acceptor = FakeAtomicAcceptor()
    request = make_request()
    scope = request.scope
    key = (scope.org_id, scope.user_id, scope.conversation_id, request.request_id)
    acceptor.records[key] = (99, "0" * 64, EXECUTION_ID, MESSAGE_ID)
    original_records = dict(acceptor.records)

    with pytest.raises(UnsupportedFingerprintVersionError):
        await RequestAcceptanceService(acceptor).accept(request)

    assert acceptor.records == original_records
    assert acceptor.turns == []
    assert acceptor.executions == []


@pytest.mark.asyncio
async def test_failed_acceptance_does_not_leave_partial_fake_state() -> None:
    acceptor = FakeAtomicAcceptor()
    acceptor.force_failure = True

    with pytest.raises(RuntimeError, match="transaction failed"):
        await RequestAcceptanceService(acceptor).accept(make_request())

    assert acceptor.records == {}
    assert acceptor.turns == []
    assert acceptor.executions == []
    assert acceptor.dispatch_eligible == set()


@pytest.mark.asyncio
async def test_conversation_busy_outcome_is_distinct_from_idempotency_conflict() -> None:
    class BusyAcceptor:
        async def accept(self, candidate: AcceptanceCandidate) -> AtomicAcceptanceRecord:
            del candidate
            return AtomicAcceptanceRecord(outcome="conversation_busy")

    with pytest.raises(ConversationBusyError, match="active execution"):
        await RequestAcceptanceService(BusyAcceptor()).accept(make_request())


def test_request_cannot_override_scope_with_additional_identity_fields() -> None:
    request = make_request()
    payload = request.model_dump()
    payload["org_id"] = "22222222-2222-2222-2222-222222222222"
    payload["user_id"] = "bbbbbbb1-1111-1111-1111-111111111111"

    with pytest.raises(ValidationError):
        InboundRequest.model_validate(payload)


def test_acceptance_candidate_requires_versioned_fingerprints() -> None:
    with pytest.raises(ValidationError):
        AcceptanceCandidate(
            request=make_request(),
            fingerprints_by_version={1: "not-a-sha256"},
        )
