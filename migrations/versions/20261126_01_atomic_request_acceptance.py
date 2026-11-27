"""Create minimum Agent-owned tables for atomic request acceptance.

Revision ID: 20261126_01
Revises:
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261126_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGENT_SCHEMA = "orchestrator"


def upgrade() -> None:
    op.create_table(
        "session_messages",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("message_order", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("message_id", name="pk_session_messages"),
        sa.UniqueConstraint("message_order", name="uq_session_messages_message_order"),
        sa.UniqueConstraint(
            "message_id",
            "org_id",
            "user_id",
            "conversation_id",
            name="uq_session_messages_scope_identity",
        ),
        schema=AGENT_SCHEMA,
    )
    op.create_table(
        "executions",
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="accepted", nullable=False),
        sa.Column("dispatch_eligible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'running', 'waiting_for_approval', 'completed', "
            "'failed', 'cancellation_requested', 'cancelled')",
            name="ck_executions_lifecycle_state",
        ),
        sa.PrimaryKeyConstraint("execution_id", name="pk_executions"),
        sa.UniqueConstraint(
            "execution_id",
            "org_id",
            "user_id",
            "conversation_id",
            name="uq_executions_scope_identity",
        ),
        schema=AGENT_SCHEMA,
    )
    op.create_table(
        "idempotency_records",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.String(length=200), nullable=False),
        sa.Column("request_id", sa.String(length=200), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint_version", sa.SmallInteger(), nullable=False),
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "fingerprint_version > 0",
            name="ck_idempotency_fingerprint_version",
        ),
        sa.CheckConstraint(
            "length(payload_fingerprint) = 64",
            name="ck_idempotency_fingerprint_length",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id", "org_id", "user_id", "conversation_id"],
            [
                "orchestrator.executions.execution_id",
                "orchestrator.executions.org_id",
                "orchestrator.executions.user_id",
                "orchestrator.executions.conversation_id",
            ],
            name="fk_idempotency_execution_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["message_id", "org_id", "user_id", "conversation_id"],
            [
                "orchestrator.session_messages.message_id",
                "orchestrator.session_messages.org_id",
                "orchestrator.session_messages.user_id",
                "orchestrator.session_messages.conversation_id",
            ],
            name="fk_idempotency_message_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "org_id",
            "user_id",
            "conversation_id",
            "request_id",
            name="pk_idempotency_records",
        ),
        schema=AGENT_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("idempotency_records", schema=AGENT_SCHEMA)
    op.drop_table("executions", schema=AGENT_SCHEMA)
    op.drop_table("session_messages", schema=AGENT_SCHEMA)
