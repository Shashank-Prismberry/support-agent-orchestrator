from uuid import UUID

import pytest
from pydantic import ValidationError

from support_agent_orchestrator.domain.context import TrustedUserContext
from support_agent_orchestrator.domain.input import (
    InvalidInternalGraphInputError,
    create_internal_graph_input,
)


def test_trusted_context_parses_contract_uuid_values_and_normalizes_json_arrays() -> None:
    context = TrustedUserContext(
        id="aaaaaaa1-1111-1111-1111-111111111111",
        email="alice@orga.com",
        full_name="Alice Admin",
        org_id="11111111-1111-1111-1111-111111111111",
        customer_id=None,
        role="Org_Admin",
        permissions=["*"],
        authorized_kb_tiers=["public", "internal_staff", "admin_only"],
    )

    assert context.id == UUID("aaaaaaa1-1111-1111-1111-111111111111")
    assert context.org_id == UUID("11111111-1111-1111-1111-111111111111")
    assert context.permissions == ("*",)
    assert context.authorized_kb_tiers == ("public", "internal_staff", "admin_only")


def test_trusted_context_rejects_invalid_uuid() -> None:
    with pytest.raises(ValidationError, match="uuid"):
        TrustedUserContext(
            id="not-a-uuid",
            email="alice@orga.com",
            full_name="Alice Admin",
            org_id="11111111-1111-1111-1111-111111111111",
            customer_id=None,
            role="Org_Admin",
            permissions=["*"],
            authorized_kb_tiers=["public"],
        )


def test_trusted_context_rejects_untrusted_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TrustedUserContext(
            id="aaaaaaa1-1111-1111-1111-111111111111",
            email="alice@orga.com",
            full_name="Alice Admin",
            org_id="11111111-1111-1111-1111-111111111111",
            customer_id=None,
            role="Org_Admin",
            permissions=["*"],
            authorized_kb_tiers=["public"],
            bearer_token="secret",
        )


def test_trusted_context_permissions_and_tiers_are_immutable(trusted_context) -> None:
    with pytest.raises(AttributeError):
        trusted_context.permissions.append("refund.issue")

    with pytest.raises(AttributeError):
        trusted_context.authorized_kb_tiers.append("admin_only")


def test_internal_input_rejects_model_construct_context_that_skipped_validation(
    user_message,
) -> None:
    forged_context = TrustedUserContext.model_construct(
        id="not-a-uuid",
        email="attacker@example.com",
        full_name="Attacker",
        org_id="also-not-a-uuid",
        customer_id=None,
        role="Org_Admin",
        permissions=["*"],
        authorized_kb_tiers=["admin_only"],
    )

    with pytest.raises(InvalidInternalGraphInputError, match="validated trusted"):
        create_internal_graph_input(user_context=forged_context, messages=[user_message])
