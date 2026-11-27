from uuid import UUID

import pytest
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable

from support_agent_orchestrator.domain.acceptance import (
    AcceptanceCandidate,
    InboundRequest,
    TrustedRequestScope,
)
from support_agent_orchestrator.infrastructure.acceptance import _resolve_existing
from support_agent_orchestrator.infrastructure.acceptance_tables import (
    executions,
    idempotency_records,
    metadata,
    session_messages,
)


def make_candidate(*, fingerprint: str = "a" * 64) -> AcceptanceCandidate:
    return AcceptanceCandidate(
        request=InboundRequest(
            scope=TrustedRequestScope(
                org_id=UUID("11111111-1111-1111-1111-111111111111"),
                user_id=UUID("aaaaaaa1-1111-1111-1111-111111111111"),
                conversation_id="conversation-unit",
            ),
            request_id="request-unit",
            message="A sanitized support request",
        ),
        fingerprints_by_version={1: fingerprint},
    )


def test_acceptance_tables_are_scoped_to_orchestrator() -> None:
    assert metadata.schema == "orchestrator"
    assert {session_messages.schema, executions.schema, idempotency_records.schema} == {
        "orchestrator"
    }
    assert [column.name for column in idempotency_records.primary_key.columns] == [
        "org_id",
        "user_id",
        "conversation_id",
        "request_id",
    ]
    assert executions.c.dispatch_eligible.server_default is not None


@pytest.mark.parametrize("table", [session_messages, executions, idempotency_records])
def test_acceptance_table_ddl_compiles_for_postgresql(table) -> None:
    ddl = str(CreateTable(table).compile(dialect=dialect()))

    assert "CREATE TABLE orchestrator." in ddl


def test_existing_matching_fingerprint_returns_original_ids() -> None:
    candidate = make_candidate()
    execution_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    message_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    result = _resolve_existing(
        {
            "fingerprint_version": 1,
            "payload_fingerprint": "a" * 64,
            "execution_id": execution_id,
            "message_id": message_id,
        },
        candidate,
    )

    assert result.outcome == "duplicate"
    assert result.execution_id == execution_id
    assert result.message_id == message_id
    assert result.stored_fingerprint_version == 1


def test_existing_different_fingerprint_returns_conflict() -> None:
    result = _resolve_existing(
        {
            "fingerprint_version": 1,
            "payload_fingerprint": "b" * 64,
            "execution_id": UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
            "message_id": UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        },
        make_candidate(),
    )

    assert result.outcome == "conflict"
    assert result.execution_id is None
    assert result.message_id is None


def test_existing_unsupported_fingerprint_version_is_not_replaced() -> None:
    result = _resolve_existing(
        {
            "fingerprint_version": 99,
            "payload_fingerprint": "a" * 64,
            "execution_id": UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
            "message_id": UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        },
        make_candidate(),
    )

    assert result.outcome == "unsupported_fingerprint_version"
    assert result.stored_fingerprint_version == 99
