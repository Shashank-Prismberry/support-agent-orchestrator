"""SQLAlchemy Core tables for atomic inbound request acceptance."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    MetaData,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)

from support_agent_orchestrator.infrastructure.database import AGENT_METADATA, AGENT_SCHEMA

metadata: MetaData = AGENT_METADATA

session_messages = Table(
    "session_messages",
    metadata,
    Column("message_id", Uuid(as_uuid=True), primary_key=True),
    Column("message_order", BigInteger, Identity(always=True), nullable=False),
    Column("org_id", Uuid(as_uuid=True), nullable=False),
    Column("user_id", Uuid(as_uuid=True), nullable=False),
    Column("conversation_id", String(200), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        "message_order",
        name="uq_session_messages_message_order",
    ),
    UniqueConstraint(
        "message_id",
        "org_id",
        "user_id",
        "conversation_id",
        name="uq_session_messages_scope_identity",
    ),
    PrimaryKeyConstraint("message_id", name="pk_session_messages"),
    schema=AGENT_SCHEMA,
)

executions = Table(
    "executions",
    metadata,
    Column("execution_id", Uuid(as_uuid=True), primary_key=True),
    Column("org_id", Uuid(as_uuid=True), nullable=False),
    Column("user_id", Uuid(as_uuid=True), nullable=False),
    Column("conversation_id", String(200), nullable=False),
    Column("status", String(32), nullable=False, server_default="accepted"),
    Column("dispatch_eligible", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint(
        "status IN ('accepted', 'running', 'waiting_for_approval', 'completed', "
        "'failed', 'cancellation_requested', 'cancelled')",
        name="ck_executions_lifecycle_state",
    ),
    UniqueConstraint(
        "execution_id",
        "org_id",
        "user_id",
        "conversation_id",
        name="uq_executions_scope_identity",
    ),
    PrimaryKeyConstraint("execution_id", name="pk_executions"),
    schema=AGENT_SCHEMA,
)

idempotency_records = Table(
    "idempotency_records",
    metadata,
    Column("org_id", Uuid(as_uuid=True), primary_key=True),
    Column("user_id", Uuid(as_uuid=True), primary_key=True),
    Column("conversation_id", String(200), primary_key=True),
    Column("request_id", String(200), primary_key=True),
    Column("execution_id", Uuid(as_uuid=True), nullable=False),
    Column("message_id", Uuid(as_uuid=True), nullable=False),
    Column("fingerprint_version", SmallInteger, nullable=False),
    Column("payload_fingerprint", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("fingerprint_version > 0", name="ck_idempotency_fingerprint_version"),
    CheckConstraint(
        "length(payload_fingerprint) = 64",
        name="ck_idempotency_fingerprint_length",
    ),
    ForeignKeyConstraint(
        ["execution_id", "org_id", "user_id", "conversation_id"],
        [
            f"{AGENT_SCHEMA}.executions.execution_id",
            f"{AGENT_SCHEMA}.executions.org_id",
            f"{AGENT_SCHEMA}.executions.user_id",
            f"{AGENT_SCHEMA}.executions.conversation_id",
        ],
        name="fk_idempotency_execution_scope",
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["message_id", "org_id", "user_id", "conversation_id"],
        [
            f"{AGENT_SCHEMA}.session_messages.message_id",
            f"{AGENT_SCHEMA}.session_messages.org_id",
            f"{AGENT_SCHEMA}.session_messages.user_id",
            f"{AGENT_SCHEMA}.session_messages.conversation_id",
        ],
        name="fk_idempotency_message_scope",
        ondelete="RESTRICT",
    ),
    PrimaryKeyConstraint(
        "org_id",
        "user_id",
        "conversation_id",
        "request_id",
        name="pk_idempotency_records",
    ),
    schema=AGENT_SCHEMA,
)
