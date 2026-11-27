from pathlib import Path
from uuid import UUID

import pytest
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from support_agent_orchestrator.domain.context import TrustedUserContext

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


@pytest.fixture
def trusted_context() -> TrustedUserContext:
    return TrustedUserContext(
        id=UUID("aaaaaaa1-1111-1111-1111-111111111111"),
        email="alice@orga.com",
        full_name="Alice Admin",
        org_id=UUID("11111111-1111-1111-1111-111111111111"),
        customer_id=None,
        role="Org_Admin",
        permissions=["*"],
        authorized_kb_tiers=["public", "internal_staff", "admin_only"],
    )


@pytest.fixture
def user_message() -> HumanMessage:
    return HumanMessage(content="I need help with my support request.", id="message-1")
