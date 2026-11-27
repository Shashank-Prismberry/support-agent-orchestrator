"""PostgreSQL-only acceptance tests; set TEST_DATABASE_URL after applying migrations."""

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, event, func, insert, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from support_agent_orchestrator.application.acceptance import (
    ConversationBusyError,
    RequestAcceptanceConflictError,
    RequestAcceptanceService,
    UnsupportedFingerprintVersionError,
)
from support_agent_orchestrator.domain.acceptance import InboundRequest, TrustedRequestScope
from support_agent_orchestrator.infrastructure.acceptance import PostgresAtomicRequestAcceptor
from support_agent_orchestrator.infrastructure.acceptance_tables import (
    executions,
    idempotency_records,
    session_messages,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ORG_A_ID = UUID("11111111-1111-1111-1111-111111111111")
ORG_B_ID = UUID("22222222-2222-2222-2222-222222222222")
ALICE_ID = UUID("aaaaaaa1-1111-1111-1111-111111111111")
BOB_ID = UUID("bbbbbbb1-1111-1111-1111-111111111111")
DAVE_ID = UUID("ddddddd2-2222-2222-2222-222222222222")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not configured for PostgreSQL integration tests",
)


@pytest_asyncio.fixture
async def postgres_acceptor() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession], PostgresAtomicRequestAcceptor]
]:
    assert TEST_DATABASE_URL is not None
    url = make_url(TEST_DATABASE_URL)
    if url.drivername != "postgresql+asyncpg" or url.database != "orchestrator_db":
        pytest.fail("TEST_DATABASE_URL must target orchestrator_db using postgresql+asyncpg")

    engine = create_async_engine(
        TEST_DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": "orchestrator"}},
    )
    try:
        async with engine.connect() as connection:
            database_name = await connection.scalar(text("SELECT current_database()"))
            schema_exists = await connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.schemata "
                    "WHERE schema_name = 'orchestrator')"
                )
            )
            if database_name != "orchestrator_db" or not schema_exists:
                pytest.fail("The configured PostgreSQL test database/schema is not provisioned")
            table_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'orchestrator' AND table_name IN "
                    "('session_messages', 'executions', 'idempotency_records')"
                )
            )
            if table_count != 3:
                pytest.fail(
                    "Apply the Agent acceptance migration before PostgreSQL integration tests"
                )
            revision = await connection.scalar(
                text("SELECT version_num FROM orchestrator.alembic_version")
            )
            if revision != "20261126_01":
                pytest.fail("The initial Agent acceptance migration revision is not recorded")

        factory = async_sessionmaker(engine, expire_on_commit=False)
        yield engine, factory, PostgresAtomicRequestAcceptor(factory)
    finally:
        await engine.dispose()


def make_request(
    *,
    scope: TrustedRequestScope | None = None,
    request_id: str | None = None,
    message: str = "Please help with this support issue.",
) -> InboundRequest:
    return InboundRequest(
        scope=scope
        or TrustedRequestScope(
            org_id=ORG_A_ID,
            user_id=ALICE_ID,
            conversation_id=f"acceptance-{uuid4()}",
        ),
        request_id=request_id or f"request-{uuid4()}",
        message=message,
    )


async def count_scope_rows(
    factory: async_sessionmaker[AsyncSession],
    scope: TrustedRequestScope,
    request_id: str,
) -> tuple[int, int, int]:
    async with factory() as session:
        async with session.begin():
            message_count = await session.scalar(
                select(func.count())
                .select_from(session_messages)
                .where(
                    session_messages.c.org_id == scope.org_id,
                    session_messages.c.user_id == scope.user_id,
                    session_messages.c.conversation_id == scope.conversation_id,
                )
            )
            execution_count = await session.scalar(
                select(func.count())
                .select_from(executions)
                .where(
                    executions.c.org_id == scope.org_id,
                    executions.c.user_id == scope.user_id,
                    executions.c.conversation_id == scope.conversation_id,
                )
            )
            record_count = await session.scalar(
                select(func.count())
                .select_from(idempotency_records)
                .where(
                    idempotency_records.c.org_id == scope.org_id,
                    idempotency_records.c.user_id == scope.user_id,
                    idempotency_records.c.conversation_id == scope.conversation_id,
                    idempotency_records.c.request_id == request_id,
                )
            )
    return int(message_count or 0), int(execution_count or 0), int(record_count or 0)


async def cleanup_scope(
    factory: async_sessionmaker[AsyncSession],
    scope: TrustedRequestScope,
    request_id: str | None,
) -> None:
    async with factory() as session:
        async with session.begin():
            idempotency_filters = [
                idempotency_records.c.org_id == scope.org_id,
                idempotency_records.c.user_id == scope.user_id,
                idempotency_records.c.conversation_id == scope.conversation_id,
            ]
            if request_id is not None:
                idempotency_filters.append(idempotency_records.c.request_id == request_id)
            await session.execute(delete(idempotency_records).where(*idempotency_filters))
            await session.execute(
                delete(executions).where(
                    executions.c.org_id == scope.org_id,
                    executions.c.user_id == scope.user_id,
                    executions.c.conversation_id == scope.conversation_id,
                )
            )
            await session.execute(
                delete(session_messages).where(
                    session_messages.c.org_id == scope.org_id,
                    session_messages.c.user_id == scope.user_id,
                    session_messages.c.conversation_id == scope.conversation_id,
                )
            )


async def seed_execution(
    factory: async_sessionmaker[AsyncSession],
    scope: TrustedRequestScope,
    status: str,
) -> UUID:
    execution_id = uuid4()
    async with factory() as session:
        async with session.begin():
            await session.execute(
                insert(executions).values(
                    execution_id=execution_id,
                    org_id=scope.org_id,
                    user_id=scope.user_id,
                    conversation_id=scope.conversation_id,
                    status=status,
                    dispatch_eligible=False,
                )
            )
    return execution_id


@pytest.mark.asyncio
async def test_postgres_first_acceptance_and_identical_duplicate(
    postgres_acceptor,
) -> None:
    _, factory, acceptor = postgres_acceptor
    request = make_request()
    service = RequestAcceptanceService(acceptor)
    try:
        first = await service.accept(request)
        duplicate = await service.accept(request)

        assert first.duplicate is False
        assert duplicate.duplicate is True
        assert duplicate.execution_id == first.execution_id
        assert duplicate.message_id == first.message_id
        assert await count_scope_rows(factory, request.scope, request.request_id) == (1, 1, 1)
    finally:
        await cleanup_scope(factory, request.scope, request.request_id)


@pytest.mark.asyncio
async def test_postgres_initial_migration_revision_is_recorded(postgres_acceptor) -> None:
    _, factory, _ = postgres_acceptor
    async with factory() as session:
        revision = await session.scalar(
            text("SELECT version_num FROM orchestrator.alembic_version")
        )

    assert revision == "20261126_01"


@pytest.mark.asyncio
async def test_postgres_same_key_different_payload_conflicts_without_mutation(
    postgres_acceptor,
) -> None:
    _, factory, acceptor = postgres_acceptor
    request = make_request()
    service = RequestAcceptanceService(acceptor)
    conflict = make_request(
        scope=request.scope,
        request_id=request.request_id,
        message="A different request payload.",
    )
    try:
        await service.accept(request)
        with pytest.raises(RequestAcceptanceConflictError):
            await service.accept(conflict)
        assert await count_scope_rows(factory, request.scope, request.request_id) == (1, 1, 1)
    finally:
        await cleanup_scope(factory, request.scope, request.request_id)


@pytest.mark.asyncio
async def test_postgres_unsupported_stored_version_is_unchanged(postgres_acceptor) -> None:
    _, factory, acceptor = postgres_acceptor
    request = make_request()
    service = RequestAcceptanceService(acceptor)
    try:
        await service.accept(request)
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    update(idempotency_records)
                    .where(
                        idempotency_records.c.org_id == request.scope.org_id,
                        idempotency_records.c.user_id == request.scope.user_id,
                        idempotency_records.c.conversation_id == request.scope.conversation_id,
                        idempotency_records.c.request_id == request.request_id,
                    )
                    .values(fingerprint_version=99)
                )

        with pytest.raises(UnsupportedFingerprintVersionError):
            await service.accept(request)

        assert await count_scope_rows(factory, request.scope, request.request_id) == (1, 1, 1)
        async with factory() as session:
            stored_version = await session.scalar(
                select(idempotency_records.c.fingerprint_version).where(
                    idempotency_records.c.org_id == request.scope.org_id,
                    idempotency_records.c.user_id == request.scope.user_id,
                    idempotency_records.c.conversation_id == request.scope.conversation_id,
                    idempotency_records.c.request_id == request.request_id,
                )
            )
        assert stored_version == 99
    finally:
        await cleanup_scope(factory, request.scope, request.request_id)


@pytest.mark.asyncio
async def test_postgres_failure_rolls_back_all_acceptance_rows(postgres_acceptor) -> None:
    engine, factory, acceptor = postgres_acceptor
    request = make_request()

    class InjectedFailure(RuntimeError):
        pass

    def fail_before_idempotency_insert(conn, cursor, statement, parameters, context, executemany):
        del conn, cursor, parameters, context, executemany
        if "INSERT INTO orchestrator.idempotency_records" in statement:
            raise InjectedFailure("injected idempotency insert failure")

    event.listen(engine.sync_engine, "before_cursor_execute", fail_before_idempotency_insert)
    try:
        with pytest.raises(InjectedFailure, match="injected idempotency insert failure"):
            await RequestAcceptanceService(acceptor).accept(request)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail_before_idempotency_insert)

    try:
        assert await count_scope_rows(factory, request.scope, request.request_id) == (0, 0, 0)
    finally:
        await cleanup_scope(factory, request.scope, request.request_id)


@pytest.mark.asyncio
async def test_postgres_concurrent_identical_submissions_create_one_acceptance(
    postgres_acceptor,
) -> None:
    _, factory, acceptor = postgres_acceptor
    request = make_request()
    service = RequestAcceptanceService(acceptor)
    try:
        first, second = await asyncio.gather(service.accept(request), service.accept(request))

        assert {first.duplicate, second.duplicate} == {False, True}
        assert first.execution_id == second.execution_id
        assert first.message_id == second.message_id
        assert await count_scope_rows(factory, request.scope, request.request_id) == (1, 1, 1)
    finally:
        await cleanup_scope(factory, request.scope, request.request_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    ["accepted", "running", "waiting_for_approval", "cancellation_requested"],
)
async def test_postgres_active_execution_rejects_new_request_without_partial_rows(
    postgres_acceptor,
    status: str,
) -> None:
    _, factory, acceptor = postgres_acceptor
    request = make_request()
    await seed_execution(factory, request.scope, status)
    try:
        with pytest.raises(ConversationBusyError):
            await RequestAcceptanceService(acceptor).accept(request)
        assert await count_scope_rows(factory, request.scope, request.request_id) == (0, 1, 0)
    finally:
        await cleanup_scope(factory, request.scope, request.request_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
async def test_postgres_terminal_execution_does_not_block_new_request(
    postgres_acceptor,
    status: str,
) -> None:
    _, factory, acceptor = postgres_acceptor
    request = make_request()
    await seed_execution(factory, request.scope, status)
    try:
        result = await RequestAcceptanceService(acceptor).accept(request)
        assert result.duplicate is False
        assert await count_scope_rows(factory, request.scope, request.request_id) == (1, 2, 1)
    finally:
        await cleanup_scope(factory, request.scope, request.request_id)


@pytest.mark.asyncio
async def test_postgres_active_duplicate_returns_original_acceptance(
    postgres_acceptor,
) -> None:
    _, factory, acceptor = postgres_acceptor
    request = make_request()
    service = RequestAcceptanceService(acceptor)
    try:
        first = await service.accept(request)
        duplicate = await service.accept(request)
        assert duplicate.duplicate is True
        assert duplicate.execution_id == first.execution_id
        assert duplicate.message_id == first.message_id
        assert await count_scope_rows(factory, request.scope, request.request_id) == (1, 1, 1)
    finally:
        await cleanup_scope(factory, request.scope, request.request_id)


@pytest.mark.asyncio
async def test_postgres_concurrent_different_requests_accept_only_one_per_conversation(
    postgres_acceptor,
) -> None:
    _, factory, acceptor = postgres_acceptor
    scope = TrustedRequestScope(
        org_id=ORG_A_ID,
        user_id=ALICE_ID,
        conversation_id=f"acceptance-race-{uuid4()}",
    )
    first_request = make_request(scope=scope)
    second_request = make_request(scope=scope)
    service = RequestAcceptanceService(acceptor)
    try:
        results = await asyncio.gather(
            service.accept(first_request),
            service.accept(second_request),
            return_exceptions=True,
        )
        accepted = [result for result in results if not isinstance(result, BaseException)]
        rejected = [result for result in results if isinstance(result, ConversationBusyError)]

        assert len(accepted) == 1
        assert len(rejected) == 1
        assert await count_scope_rows(factory, scope, first_request.request_id) == (1, 1, 1)
        assert await count_scope_rows(factory, scope, second_request.request_id) == (1, 1, 0)
        assert await count_scope_rows(factory, scope, "unused-request-id") == (1, 1, 0)
    finally:
        await cleanup_scope(factory, scope, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_field", ["org_id", "user_id", "conversation_id"])
async def test_postgres_request_keys_are_isolated_by_each_scope_field(
    postgres_acceptor,
    scope_field: str,
) -> None:
    _, factory, acceptor = postgres_acceptor
    first_request = make_request()
    updates: dict[str, UUID | str]
    if scope_field == "org_id":
        updates = {"org_id": ORG_B_ID, "user_id": DAVE_ID}
    elif scope_field == "user_id":
        updates = {"user_id": BOB_ID}
    else:
        updates = {"conversation_id": f"other-{uuid4()}"}
    second_scope = first_request.scope.model_copy(update=updates)
    second_request = make_request(
        scope=second_scope,
        request_id=first_request.request_id,
        message=first_request.message,
    )
    service = RequestAcceptanceService(acceptor)
    try:
        first = await service.accept(first_request)
        second = await service.accept(second_request)

        assert first.duplicate is False
        assert second.duplicate is False
        assert first.execution_id != second.execution_id
        assert await count_scope_rows(factory, first_request.scope, first_request.request_id) == (
            1,
            1,
            1,
        )
        assert await count_scope_rows(factory, second_scope, second_request.request_id) == (
            1,
            1,
            1,
        )
    finally:
        await cleanup_scope(factory, first_request.scope, first_request.request_id)
        await cleanup_scope(factory, second_scope, second_request.request_id)
